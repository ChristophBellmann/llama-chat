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
        self.benchmark_active = False

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
                    'requested': self.requested, 'error': self.error,
                    'voice': self.voice(self.requested if self.state in ('lädt', 'stellt wieder her') else active)}

    def voice(self, model):
        profiles = self.root / 'profiles/model-settings.json'
        data = json.loads(profiles.read_text()) if profiles.exists() else {}
        voice = data.get('models', {}).get(model, {}).get('voice', 'orpheus')
        if voice not in ('ramona', 'orpheus'):
            raise ValueError('Unbekannte Stimme im Modellprofil')
        return voice

    def prepare_services(self, model):
        # Das alte LLM zuerst freigeben: auch die Rückkehr zu Orpheus muss passen.
        self.systemctl('stop', 'llama-server.service')
        if self.voice(model) == 'ramona':
            self.systemctl('stop', 'wyoming-orpheus.service', 'orpheus-llm.service')
        else:
            self.systemctl('start', 'orpheus-llm.service', 'wyoming-orpheus.service')

    def check_idle(self):
        for port in ((8080,) if self.voice(self.status()['active']) == 'ramona' else (8080, 8082)):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/slots', timeout=2) as response:
                slots = json.load(response)
            if not isinstance(slots, list) or not slots or any(
                    slot.get('is_processing') is not False for slot in slots):
                raise RuntimeError('Modellaktivität unbekannt oder beschäftigt')

    def start(self, model):
        with self.lock:
            if model not in self.catalog():
                return 400, {'error': 'Unbekanntes Modell'}
            if self.state in ('lädt', 'stellt wieder her'):
                return 409, {'error': 'Ein Modellwechsel läuft bereits'}
            if self.benchmark_active:
                return 409, {'error': 'Modellvergleich läuft; zuerst abbrechen'}
            try:
                self.check_idle()
            except Exception:
                return 409, {'error': 'Modellaktivität unbekannt oder beschäftigt; erst Dienste prüfen'}
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
                    if self.voice(model) == 'orpheus':
                        with urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=2) as response:
                            if json.load(response).get('status') != 'ok':
                                continue
                    return
            except Exception:
                pass
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        raise RuntimeError('Das gewählte Modell wurde nicht rechtzeitig bereit')

    @staticmethod
    def quote(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')

    def settings(self, model):
        path = (self.root / 'models' / model).resolve()
        values = {'GPU_LAYERS': 20 if path.stat().st_size > 12 * 1024**3 else -1,
                  'CTX': 8192, 'PARALLEL': 1, 'BATCH_SIZE': 512, 'UBATCH_SIZE': 256}
        profiles = self.root / 'profiles/model-settings.json'
        if profiles.exists():
            data = json.loads(profiles.read_text())
            if data.get('version') != 1:
                raise ValueError('Unbekannte Modellprofil-Version')
            values.update(data.get('defaults', {}))
            values.update(data.get('models', {}).get(model, {}).get('settings', {}))
        numeric = {'CTX': (512, 262144), 'PARALLEL': (1, 16),
                   'BATCH_SIZE': (1, 8192), 'UBATCH_SIZE': (1, 8192),
                   'LLAMA_ARG_FIT_TARGET': (0, 32768), 'LLAMA_ARG_LOG_VERBOSITY': (0, 10)}
        choices = {'GPU_LAYERS': {'auto'}, 'LLAMA_ARG_FIT': {'on', 'off'},
                   'CACHE_TYPE_K': {'f16', 'bf16', 'q8_0', 'q4_0', 'q4_1', 'q5_0', 'q5_1', 'iq4_nl'},
                   'CACHE_TYPE_V': {'f16', 'bf16', 'q8_0', 'q4_0', 'q4_1', 'q5_0', 'q5_1', 'iq4_nl'},
                   'GGML_CUDA_DISABLE_GRAPHS': {0, 1, '0', '1'}}
        for key, value in values.items():
            if key in numeric:
                lower, upper = numeric[key]
                valid = type(value) is int and lower <= value <= upper
            elif key == 'GPU_LAYERS' and type(value) is int:
                valid = -1 <= value <= 999
            elif key in choices:
                valid = isinstance(value, (str, int)) and value in choices[key]
            else:
                valid = False
            if not valid:
                raise ValueError(f'Ungültige Modelleinstellung: {key}')
        if values['UBATCH_SIZE'] > values['BATCH_SIZE'] or values['CTX'] // values['PARALLEL'] < 512:
            raise ValueError('Unpassende Kontext-/Batch-Einstellungen')
        return values

    def change(self, model):
        previous = self.dropin.read_bytes() if self.dropin.exists() else None
        old_model = self.status()['active']
        with self.lock:
            self.state, self.requested = 'lädt', model
        try:
            path = (self.root / 'models' / model).resolve()
            settings = self.settings(model)
            self.dropin.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.dropin.with_suffix('.tmp')
            temporary.write_text('[Service]\n' + '\n'.join(
                f'Environment="{key}={self.quote(value)}"' for key, value in {'MODEL_PATH': path, **settings}.items()) + '\n')
            temporary.replace(self.dropin)
            self.systemctl('daemon-reload')
            self.prepare_services(model)
            self.systemctl('restart', 'llama-server.service')
            self.wait_ready(path.name)
            with self.lock:
                self.state, self.error = 'bereit', ''
        except Exception:
            with self.lock:
                self.state, self.error = 'stellt wieder her', 'Modellwechsel fehlgeschlagen; vorherige Einstellung wird wiederhergestellt'
                self.requested = old_model
            try:
                if previous is None:
                    self.dropin.unlink(missing_ok=True)
                else:
                    self.dropin.write_bytes(previous)
                self.systemctl('daemon-reload')
                self.prepare_services(old_model)
                self.systemctl('restart', 'llama-server.service')
                self.wait_ready(old_model)
                with self.lock:
                    self.state, self.error = 'Fehler', 'Modellwechsel fehlgeschlagen; vorheriges Modell läuft wieder'
            except Exception:
                with self.lock:
                    self.state, self.error = 'Fehler', 'Auch die Wiederherstellung ist fehlgeschlagen; llama-server prüfen'
