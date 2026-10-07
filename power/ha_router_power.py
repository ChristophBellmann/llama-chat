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
            if self.ready():
                return True
            deadline = time.monotonic() + self.config.get("wake_timeout", 45)
            while time.monotonic() < deadline:
                try:
                    self.send_magic_packet()
                except OSError:
                    return False
                if self.ready():
                    return True
                time.sleep(min(2, max(0, deadline - time.monotonic())))
            return False

    @contextlib.contextmanager
    def request(self, use_workstation=True):
        if not use_workstation or not self.config:
            yield
            return
        with self.lock:
            self.active_requests += 1
            self.last_use = time.monotonic()
        try:
            self.wake()
            yield
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
                    "/workstation/suspend-idle", "/workstation/models"):
        return False
    if handler.command == "POST" and path != "/workstation/models":
        handler._discard_declared_body()
    if handler.client_address[0] not in ("127.0.0.1", "::1"):
        if handler.command == "POST" and path == "/workstation/models":
            handler._discard_declared_body()
        handler._json_response(403, {"error": "Nur Home Assistant auf dem Server darf steuern"})
        return True
    power = handler.router.workstation_power
    if path == "/workstation/models" and handler.command in ("GET", "POST"):
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
    elif handler.command == "GET" and path == "/workstation":
        handler._json_response(200, power.status())
    elif handler.command == "POST" and path == "/workstation/wake":
        with power.request():
            ready = power.ready()
        handler._json_response(200 if ready else 503, {"ready": ready})
    elif handler.command == "POST" and path in ("/workstation/suspend", "/workstation/suspend-idle"):
        status, payload = power.suspend(automatic=path.endswith("-idle"))
        handler._json_response(status, payload)
    else:
        handler._json_response(405, {"error": "Methode nicht erlaubt"})
    return True
