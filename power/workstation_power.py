#!/usr/bin/env python3
"""Beschränkte Standby-Schnittstelle für Home Assistant (nur Standardbibliothek)."""

import hmac
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.request

try:
    from .model_control import ModelControl
except ImportError:
    from model_control import ModelControl


def activity():
    reasons = []
    for port in (8080, 8082):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/slots", timeout=2) as response:
                slots = json.load(response)
            if not isinstance(slots, list) or not slots:
                raise ValueError("Keine Slots")
            if any(slot.get("is_processing") is not False for slot in slots):
                reasons.append(f"Modell auf Port {port} arbeitet")
        except Exception:
            reasons.append(f"Modellaktivität auf Port {port} unbekannt")
    gpu_paths = list(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))
    if not gpu_paths:
        reasons.append("GPU-Auslastung unbekannt")
    for path in gpu_paths:
        try:
            if int(path.read_text()) > 5:
                reasons.append("GPU arbeitet")
        except (OSError, ValueError):
            reasons.append("GPU-Auslastung unbekannt")
    if os.getloadavg()[0] > max(1, (os.cpu_count() or 1) * 0.25):
        reasons.append("CPU arbeitet")
    try:
        result = subprocess.run(
            ["pactl", "-f", "json", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        if any(stream.get("corked") is not True for stream in json.loads(result.stdout)):
            reasons.append("Audioausgabe läuft")
    except (OSError, ValueError, subprocess.SubprocessError):
        reasons.append("Audioaktivität unbekannt")
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.cinnamon.Muffin.IdleMonitor",
             "--object-path", "/org/cinnamon/Muffin/IdleMonitor/Core", "--method",
             "org.cinnamon.Muffin.IdleMonitor.GetIdletime"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        match = re.fullmatch(r"\(uint64 (\d+),\)\s*", result.stdout)
        desktop_idle = int(match[1]) // 1000 if match else None
    except (OSError, subprocess.SubprocessError):
        desktop_idle = None
    return {"busy": bool(reasons), "reasons": reasons, "desktop_idle_seconds": desktop_idle}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass  # Header und Schlüssel gehören nicht ins Journal.

    def authorized(self):
        return (self.client_address[0] == self.server.ha_host
                and hmac.compare_digest(self.headers.get("Authorization", ""),
                                        f"Bearer {self.server.token}"))

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        if not self.authorized():
            self.reply(403, {"error": "Nicht erlaubt"})
        elif self.path == "/models":
            self.reply(200, self.server.models.status())
        elif self.path == "/status":
            self.reply(200, activity())
        else:
            self.reply(404, {"error": "Unbekannter Pfad"})

    def do_POST(self):
        if not self.authorized():
            self.reply(403, {"error": "Nicht erlaubt"})
            return
        if self.path == "/models":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2048:
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
                model = payload.get("model")
                if not isinstance(model, str):
                    raise ValueError()
            except (ValueError, AttributeError):
                self.reply(400, {"error": "Ungültige Modellauswahl"})
                return
            with self.server.sleep_lock:
                status, payload = self.server.models.start(model)
            self.reply(status, payload)
            return
        if self.path not in ("/suspend", "/suspend-idle"):
            self.reply(404, {"error": "Unbekannter Pfad"})
            return
        with self.server.sleep_lock:
            if getattr(getattr(self.server, "models", None), "state", None) in ("lädt", "stellt wieder her"):
                self.reply(409, {"error": "Modellwechsel läuft"})
                return
            state = activity()
            if self.path == "/suspend-idle" and (
                state["desktop_idle_seconds"] is None or state["desktop_idle_seconds"] < 1800
            ):
                state["reasons"].append("Desktop nicht seit 30 Minuten unbenutzt")
            if state["reasons"]:
                self.reply(409, state)
                return
            result = subprocess.run(
                ["sudo", "-n", "/usr/bin/systemctl", "--no-block", "suspend"],
                capture_output=True, timeout=10,
            )
            self.reply(202 if result.returncode == 0 else 503,
                       {"accepted": result.returncode == 0,
                        "error": None if result.returncode == 0 else "Standby-Rechte fehlen"})


if __name__ == "__main__":
    config = json.loads(Path(os.environ["WORKSTATION_POWER_CONFIG"]).read_text())
    server = http.server.ThreadingHTTPServer((config["bind"], 8091), Handler)
    server.ha_host = config["ha_host"]
    server.token = config["token"]
    server.sleep_lock = threading.Lock()
    server.models = ModelControl()
    server.serve_forever()
