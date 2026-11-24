"""Aufwecken und Standby über den bestehenden HA-LLM-Router."""

import contextlib
import http.client
import json
import os
from pathlib import Path
import socket
import threading
import time
import urllib.error
import urllib.request


class WorkstationPower:
    def __init__(self, config=None):
        self.config = config
        self.lock = threading.RLock()
        self.wake_lock = threading.Lock()
        self.active_requests = 0
        self.last_use = time.monotonic()
        # Nach einem gescheiterten Weckversuch bis zu diesem Zeitpunkt nicht
        # erneut warten: ist die Workstation ganz aus oder außer Haus, kostete
        # sonst jede Sprachanfrage die volle Weckzeit, bevor der Fallback kam.
        self.wake_failed_until = 0.0
        self.benchmark_revision = 0
        self.benchmark_cache = {"status": "noch nicht gemessen", "results": []}
        self.model_cache = {"models": [], "active": None, "status": "nicht erreichbar", "error": ""}

    @classmethod
    def from_environment(cls):
        path = os.getenv("LLM_ROUTER_POWER_CONFIG")
        if path:
            return cls(json.loads(Path(path).read_text()))
        token = os.getenv("LLM_ROUTER_POWER_TOKEN")
        return cls({
            "token": token,
            "mac": os.getenv("LLM_ROUTER_WOL_MAC", "c8:b2:9b:df:73:20"),
            "broadcast": os.getenv("LLM_ROUTER_WOL_BROADCAST", "192.168.178.255"),
            "health_url": os.getenv("LLM_ROUTER_WAKE_HEALTH_URL", "http://192.168.178.51:8080/health"),
            "power_url": os.getenv("LLM_ROUTER_POWER_URL", "http://192.168.178.51:8091"),
        } if token else None)

    def ready(self):
        if not self.config:
            return False
        try:
            with urllib.request.urlopen(self.config["health_url"], timeout=2) as response:
                return response.status == 200 and json.load(response).get("status") == "ok"
        except (OSError, ValueError, http.client.HTTPException):
            return False

    def llm_off(self):
        """Wach, aber mit „Keines“ bewusst ohne LLM: dann antwortet 8080 nie."""
        if not self.config or not self.config.get("power_url") or not self.config.get("token"):
            return False
        request = urllib.request.Request(
            self.config["power_url"] + "/models",
            headers={"Authorization": "Bearer " + self.config["token"]})
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return json.load(response).get("status") == "aus"
        except (OSError, ValueError, http.client.HTTPException, AttributeError):
            return False

    def awake(self):
        return self.ready() or self.llm_off()

    def send_magic_packet(self):
        mac = bytes.fromhex(self.config["mac"].replace(":", "").replace("-", ""))
        if len(mac) != 6:
            raise ValueError("Ungültige WLAN-MAC")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(b"\xff" * 6 + mac * 16, (self.config["broadcast"], 9))

    def wake(self):
        if not self.config:
            return False
        with self.wake_lock:
            if self.awake():
                self.wake_failed_until = 0.0
                return True
            if time.monotonic() < self.wake_failed_until:
                return False
            deadline = time.monotonic() + self.config.get("wake_timeout", 45)
            while time.monotonic() < deadline:
                try:
                    self.send_magic_packet()
                except OSError:
                    break
                if self.awake():
                    return True
                time.sleep(min(2, max(0, deadline - time.monotonic())))
            self.wake_failed_until = time.monotonic() + self.config.get("wake_retry_after", 600)
            return False

    @contextlib.contextmanager
    def request(self, use_workstation=True, *, wait_for_ready=True):
        if not use_workstation or not self.config:
            yield
            return
        with self.lock:
            self.active_requests += 1
            self.last_use = time.monotonic()
        try:
            if wait_for_ready:
                _, benchmark = self.benchmark()
            else:
                # Voice nutzt die Hintergrundprüfung. Keine Netzabfrage und
                # kein Aufwecken im Anfragepfad, Reservierung bleibt erhalten.
                with self.lock:
                    benchmark = dict(self.benchmark_cache)
            benchmarking = benchmark.get('status') in ('läuft', 'stellt wieder her')
            if wait_for_ready and not benchmarking:
                self.wake()
            yield benchmarking
        finally:
            with self.lock:
                self.active_requests -= 1
                self.last_use = time.monotonic()

    def status(self):
        with self.lock:
            return {"configured": bool(self.config), "active_requests": self.active_requests,
                    "idle_seconds": int(time.monotonic() - self.last_use)}

    def models(self, model=None):
        if not self.config:
            return 503, {"error": "Workstation-Steuerung ist nicht eingerichtet"}
        if model is not None:
            with self.lock:
                if self.active_requests:
                    return 409, {"error": "LLM wird noch benutzt"}
                self.last_use = time.monotonic()
            if not self.wake():
                return 503, {"error": "Workstation konnte nicht aufgeweckt werden"}
        request = urllib.request.Request(
            self.config["power_url"] + "/models",
            data=json.dumps({"model": model}).encode() if model is not None else None,
            headers={"Authorization": "Bearer " + self.config["token"],
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.load(response)
                self.model_cache = payload
                return response.status, payload
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            finally:
                error.close()
        except (OSError, ValueError, http.client.HTTPException):
            if model is None:
                return 200, {**self.model_cache, "ready": False,
                             "status": "nicht erreichbar", "error": "Workstation schläft oder ist nicht erreichbar"}
            return 503, {"error": "Modellschnittstelle nicht erreichbar"}

    def voice(self, voice):
        """Orpheus auf der Workstation aus- („keine“) oder wieder zulassen."""
        if not self.config:
            return 503, {"error": "Workstation-Steuerung ist nicht eingerichtet"}
        if not self.wake():
            return 503, {"error": "Workstation konnte nicht aufgeweckt werden"}
        request = urllib.request.Request(
            self.config["power_url"] + "/voice",
            data=json.dumps({"voice": voice}).encode(),
            headers={"Authorization": "Bearer " + self.config["token"],
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = json.load(response)
                self.model_cache = payload
                return response.status, payload
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            finally:
                error.close()
        except (OSError, ValueError, http.client.HTTPException):
            return 503, {"error": "Stimmschnittstelle nicht erreichbar"}

    def benchmark(self, action=None, models=None):
        if not self.config or not self.config.get("power_url"):
            if action is None:
                return 200, {"status": "nicht eingerichtet", "results": []}
        if not self.config or not self.config.get("power_url"):
            return 503, {"error": "Workstation-Steuerung ist nicht eingerichtet"}
        if action == 'start':
            with self.lock:
                if self.active_requests:
                    return 409, {"error": "LLM wird noch benutzt"}
            if not self.wake():
                return 503, {"error": "Workstation konnte nicht aufgeweckt werden"}
            # Zwischen Prüfung und Reservierung darf keine neue Inferenz starten.
            with self.lock:
                if self.active_requests:
                    return 409, {"error": "LLM wird noch benutzt"}
                self.last_use = time.monotonic()
                return self._benchmark_http(action, models)
        return self._benchmark_http(action, models)

    def _benchmark_http(self, action, models):
        with self.lock:
            if action:
                self.benchmark_revision += 1
            revision = self.benchmark_revision
        suffix = '/benchmark/stop' if action == 'stop' else '/benchmark'
        request = urllib.request.Request(
            self.config['power_url'] + suffix,
            data=json.dumps({'models': models}).encode() if action else None,
            headers={'Authorization': 'Bearer ' + self.config['token'],
                     'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=6 if action else 1) as response:
                payload = json.load(response)
                if action != 'stop':
                    with self.lock:
                        if revision == self.benchmark_revision:
                            self.benchmark_cache = payload
                return response.status, payload
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            finally:
                error.close()
        except (OSError, ValueError, http.client.HTTPException):
            if action is None:
                return 200, {**self.benchmark_cache, 'offline': True}
            return 503, {'error': 'Modellvergleich nicht erreichbar'}

    def suspend(self, automatic=False):
        if not self.config:
            return 503, {"error": "Standby ist nicht eingerichtet"}
        with self.lock:
            state = self.status()
            minimum_idle = 1800 if automatic else 10
            if state["active_requests"] or state["idle_seconds"] < minimum_idle:
                return 409, {"error": "LLM wird noch benutzt", **state}
            request = urllib.request.Request(
                self.config["power_url"] + ("/suspend-idle" if automatic else "/suspend"),
                data=b"", headers={"Authorization": "Bearer " + self.config["token"]},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                try:
                    return error.code, json.load(error)
                finally:
                    error.close()
            except (OSError, ValueError, http.client.HTTPException):
                return 503, {"error": "Standby-Schnittstelle nicht erreichbar"}


def handle_power(handler):
    """Wird vor den vorhandenen GET/POST-Routen aufgerufen."""
    path = handler.path.split("?", 1)[0]
    if path not in ("/workstation", "/workstation/wake", "/workstation/suspend",
                    "/workstation/suspend-idle", "/workstation/models", "/workstation/voice",
                    "/workstation/benchmark", "/workstation/benchmark/stop"):
        return False
    if handler.command == "POST" and path not in ("/workstation/models", "/workstation/voice", "/workstation/benchmark"):
        handler._discard_declared_body()
    if handler.client_address[0] not in ("127.0.0.1", "::1"):
        if handler.command == "POST" and path in ("/workstation/models", "/workstation/voice", "/workstation/benchmark"):
            handler._discard_declared_body()
        handler._json_response(403, {"error": "Nur Home Assistant auf dem Server darf steuern"})
        return True
    power = handler.router.workstation_power
    if path in ("/workstation/benchmark", "/workstation/benchmark/stop"):
        models = None
        if handler.command == 'POST' and path.endswith('/benchmark'):
            body = handler._read_request_body()
            if body is None:
                return True
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError()
                models = payload.get('models')
            except ValueError:
                handler._json_response(400, {'error': 'Ungültiger Vergleichsauftrag'})
                return True
        if handler.command == 'GET' and path.endswith('/benchmark'):
            status, payload = power.benchmark()
        elif handler.command == 'POST':
            status, payload = power.benchmark('stop' if path.endswith('/stop') else 'start', models)
        else:
            status, payload = 405, {'error': 'Methode nicht erlaubt'}
        handler._json_response(status, payload)
    elif path == "/workstation/models" and handler.command in ("GET", "POST"):
        model = None
        if handler.command == "POST":
            body = handler._read_request_body()
            if body is None:
                return True
            try:
                model = json.loads(body).get("model")
                if not isinstance(model, str) or len(model) > 200:
                    raise ValueError()
            except (ValueError, AttributeError):
                handler._json_response(400, {"error": "Ungültige Modellauswahl"})
                return True
        status, payload = power.models(model)
        handler._json_response(status, payload)
    elif path == "/workstation/voice" and handler.command == "POST":
        body = handler._read_request_body()
        if body is None:
            return True
        try:
            voice = json.loads(body).get("voice")
            if voice not in ("keine", "orpheus"):
                raise ValueError()
        except (ValueError, AttributeError):
            handler._json_response(400, {"error": "Ungültige Stimmwahl"})
            return True
        status, payload = power.voice(voice)
        handler._json_response(status, payload)
    elif handler.command == "GET" and path == "/workstation":
        handler._json_response(200, power.status())
    elif handler.command == "POST" and path == "/workstation/wake":
        # Der Aufweckknopf versucht es immer, auch in der Sperrzeit.
        power.wake_failed_until = 0.0
        with power.request():
            ready = power.ready()
        handler._json_response(200 if ready else 503, {"ready": ready})
    elif handler.command == "POST" and path in ("/workstation/suspend", "/workstation/suspend-idle"):
        status, payload = power.suspend(automatic=path.endswith("-idle"))
        handler._json_response(status, payload)
    else:
        handler._json_response(405, {"error": "Methode nicht erlaubt"})
    return True
