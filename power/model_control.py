"""Modellwechsel für den gemeinsamen llama-server, ohne Shell-Befehle vom Client."""
import json
from pathlib import Path
import subprocess
import re
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class ModelControl:
    def __init__(self, root=ROOT, dropin=None):
        self.root = Path(root)
        self.dropin = dropin or Path.home() / '.config/systemd/user/llama-server.service.d/zz-ha-model.conf'
        self.lock = threading.RLock()
        self.state = 'bereit'
        self.error = ''
        self.requested = None

    def catalog(self):
        models, seen = [], set()
        base = (self.root / 'models').resolve()
        for path in sorted(base.glob('*.gguf')):
            resolved = path.resolve()
            if (not resolved.is_file() or resolved.parent != base or resolved in seen
                    or not re.fullmatch(r"[\w.+ -]+\.gguf", resolved.name)):
                continue
            seen.add(resolved)
            models.append(resolved.name)
        return sorted(models)

    def props(self):
        with urllib.request.urlopen('http://127.0.0.1:8080/props', timeout=2) as response:
            return json.load(response)

    def status(self):
        try:
            props = self.props()
            active = Path(props['model_path']).name
            ready = True
        except Exception:
            active, ready = None, False
        with self.lock:
            return {'models': self.catalog(), 'active': active, 'ready': ready,
                    'status': self.state if self.state != 'bereit' or ready else 'nicht bereit',
                    'requested': self.requested, 'error': self.error}

    def start(self, model):
        with self.lock:
            if model not in self.catalog():
                return 400, {'error': 'Unbekanntes Modell'}
            if self.state in ('lädt', 'stellt wieder her'):
                return 409, {'error': 'Ein Modellwechsel läuft bereits'}
            # Auch direkt verbundene Textchat-/TTS-Clients berücksichtigen.
            try:
                for port in (8080, 8082):
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/slots', timeout=2) as response:
                        slots = json.load(response)
                        if not isinstance(slots, list) or not slots:
                            raise ValueError('Keine Slots')
                        if any(slot.get('is_processing') is not False for slot in slots):
                            return 409, {'error': 'Ein Modell bearbeitet gerade eine Anfrage'}
            except Exception:
                return 409, {'error': 'Modellaktivität unbekannt; erst Dienste prüfen'}
            current = self.status()
            if not current['ready']:
                return 409, {'error': 'Der LLM-Server ist noch nicht bereit'}
            if current['active'] == model:
                self.state, self.error = 'bereit', ''
                return 200, self.status()
            self.state, self.error, self.requested = 'lädt', '', model
            threading.Thread(target=self.change, args=(model,), daemon=True).start()
            return 202, self.status()

    def systemctl(self, *args):
        subprocess.run(['systemctl', '--user', *args], check=True, capture_output=True, timeout=30)

    def wait_ready(self, model, timeout=150):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2) as response:
                    healthy = json.load(response).get('status') == 'ok'
                if healthy and Path(self.props()['model_path']).name == model:
                    return
            except Exception:
                pass
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        raise RuntimeError('Das gewählte Modell wurde nicht rechtzeitig bereit')

    @staticmethod
    def quote(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')

    def change(self, model):
        previous = self.dropin.read_bytes() if self.dropin.exists() else None
        old_model = self.status()['active']
        try:
            path = (self.root / 'models' / model).resolve()
            # Große Dateien passen nicht vollständig neben Desktop und Orpheus in 12 GB VRAM.
            layers = 20 if path.stat().st_size > 12 * 1024**3 else -1
            self.dropin.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.dropin.with_suffix('.tmp')
            temporary.write_text('[Service]\n' + '\n'.join(
                f'Environment="{key}={self.quote(value)}"' for key, value in {
                    'MODEL_PATH': path, 'GPU_LAYERS': layers, 'CTX': 8192,
                    'PARALLEL': 1, 'BATCH_SIZE': 512, 'UBATCH_SIZE': 256,
                }.items()) + '\n')
            temporary.replace(self.dropin)
            self.systemctl('daemon-reload')
            self.systemctl('restart', 'llama-server.service')
            self.wait_ready(path.name)
            with self.lock:
                self.state, self.error = 'bereit', ''
        except Exception:
            with self.lock:
                self.state, self.error = 'stellt wieder her', 'Modellwechsel fehlgeschlagen; vorherige Einstellung wird wiederhergestellt'
            try:
                if previous is None:
                    self.dropin.unlink(missing_ok=True)
                else:
                    self.dropin.write_bytes(previous)
                self.systemctl('daemon-reload')
                self.systemctl('restart', 'llama-server.service')
                self.wait_ready(old_model)
                with self.lock:
                    self.state, self.error = 'Fehler', 'Modellwechsel fehlgeschlagen; vorheriges Modell läuft wieder'
            except Exception:
                with self.lock:
                    self.state, self.error = 'Fehler', 'Auch die Wiederherstellung ist fehlgeschlagen; llama-server prüfen'
