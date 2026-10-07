"""Serieller Modellvergleich auf der Workstation, unabhängig von HA-Neustarts."""
import copy
import base64
from datetime import datetime
import http.client
import json
from pathlib import Path
import statistics
import socket
import threading
import time
import urllib.request

BUSY = ('läuft', 'stellt wieder her')
PROMPT = 'Erkläre in vier kurzen Sätzen, wie eine Wärmepumpe ein Haus heizt. Verwende keine Aufzählung.'


def gpu_memory():
    """Gesamter belegter dedizierter VRAM; Desktop und Orpheus sind enthalten."""
    devices = sorted(Path('/sys/class/drm').glob('card*/device/mem_info_vram_used'))
    if not devices:
        raise RuntimeError('VRAM-Messung ist auf dieser GPU nicht verfügbar')
    used = sum(int(path.read_text()) for path in devices)
    total = sum(int(path.with_name('mem_info_vram_total').read_text()) for path in devices)
    return {'used_mib': round(used / 1024**2, 1), 'total_mib': round(total / 1024**2, 1)}


def measure(cancel, limit=120):
    payload = {'model': 'locales_llm', 'messages': [
        {'role': 'system', 'content': 'Antworte kurz und sachlich auf Deutsch.'},
        {'role': 'user', 'content': PROMPT}], 'temperature': 0, 'seed': 42,
        'max_tokens': 96, 'stream': True, 'stream_options': {'include_usage': True},
        'cache_prompt': False}
    started = time.monotonic()
    connection = http.client.HTTPConnection('127.0.0.1', 8080, timeout=limit)
    watchdog_stop = threading.Event()
    watchdog = None
    first, usage, timings, text, finished = None, {}, {}, '', False
    try:
        connection.connect()
        transport = connection.sock
        def interrupt():
            while not watchdog_stop.wait(0.1):
                if cancel.is_set() or time.monotonic() - started >= limit:
                    try:
                        transport.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    return
        watchdog = threading.Thread(target=interrupt, daemon=True)
        watchdog.start()
        connection.request('POST', '/v1/chat/completions', body=json.dumps(payload),
                           headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f'Inferenz: HTTP {response.status}')
        while True:
            if cancel.is_set():
                raise InterruptedError('Abbruch angefordert')
            remaining = limit - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('Inferenz-Zeitlimit erreicht')
            transport.settimeout(remaining)
            line = response.readline()
            if cancel.is_set():
                raise InterruptedError('Abbruch angefordert')
            if not line:
                break
            if not line.startswith(b'data:'):
                continue
            data = line[5:].strip()
            if data == b'[DONE]':
                finished = True
                break
            chunk = json.loads(data)
            delta = (chunk.get('choices') or [{}])[0].get('delta') or {}
            content = delta.get('content') or ''
            if content and first is None:
                first = time.monotonic() - started
            text += content
            usage = chunk.get('usage') or usage
            timings = chunk.get('timings') or timings
        elapsed = time.monotonic() - started
        if not finished or first is None or not text.strip():
            raise RuntimeError('Keine vollständige Textantwort erhalten')
        tokens = usage.get('completion_tokens') or timings.get('predicted_n')
        speed = timings.get('predicted_per_second')
        if not speed and tokens and elapsed > first:
            speed = max(0, tokens - 1) / (elapsed - first)
        return {'ttft_s': round(first, 3), 'total_s': round(elapsed, 3),
                'tokens_s': round(speed, 2) if speed else None, 'tokens': tokens}
    finally:
        watchdog_stop.set()
        connection.close()
        if watchdog:
            watchdog.join(timeout=1)


class ModelBenchmark:
    def __init__(self, controller, output=None):
        self.controller = controller
        self.output = output or Path.home() / '.config/workstation-power/benchmark.json'
        self.recovery = self.output.with_suffix(".recovery.json")
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.data = {'status': 'noch nicht gemessen', 'results': [], 'error': ''}
        if self.output.exists():
            try:
                self.data = json.loads(self.output.read_text())
                if self.data['status'] in BUSY:
                    self.data.update(status='unterbrochen', error='Dienst wurde während des Vergleichs beendet; Modellzustand prüfen')
            except (ValueError, KeyError):
                pass

        if self.recovery.exists():
            snapshot = json.loads(self.recovery.read_text())
            previous = base64.b64decode(snapshot['configuration']) if snapshot['configuration'] is not None else None
            controller.benchmark_active = True
            self.cancel.set()
            self.publish(status='stellt wieder her', error='Unterbrochenen Vergleich wiederherstellen')
            threading.Thread(target=self.run, args=([], snapshot['model'], previous), daemon=True).start()

    def status(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def publish(self, **values):
        with self.lock:
            self.data.update(values)
            self.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.output.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
            temporary.chmod(0o600)
            temporary.replace(self.output)

    def start(self, models=None):
        control = self.controller
        with control.lock:
            if control.benchmark_active or control.state in ('lädt', 'stellt wieder her'):
                return 409, {'error': 'Ein Modellwechsel oder Vergleich läuft bereits'}
            catalog = control.catalog()
            if models is not None and (not isinstance(models, list) or not models or
                                       any(not isinstance(m, str) or m not in catalog for m in models)):
                return 400, {'error': 'Ungültige Modellliste'}
            selected = list(dict.fromkeys(models)) if models is not None else catalog
            if not selected:
                return 409, {'error': 'Keine Modelle vorhanden'}
            current = control.status()
            if not current['ready']:
                return 409, {'error': 'LLM-Server ist noch nicht bereit'}
            try:
                gpu_memory()
                control.check_idle()
            except Exception:
                return 409, {'error': 'GPU oder Modellaktivität nicht bereit; laufende Anfragen zuerst beenden'}
            # Snapshot vor dem Threadstart: exakt dieselben Einstellungen zurückgeben.
            original = current['active']
            previous = control.dropin.read_bytes() if control.dropin.exists() else None
            self.cancel.clear()
            try:
                self.publish(status='läuft', results=[], error='', current=None, completed=0,
                             total=len(selected), started=datetime.now().astimezone().isoformat(timespec='seconds'),
                             original=original, restored=False, rounds=3, warmups=2, finished=None, offline=False)
                snapshot = self.recovery.with_suffix('.tmp')
                snapshot.write_text(json.dumps({'model': original, 'configuration':
                    base64.b64encode(previous).decode() if previous is not None else None}))
                snapshot.chmod(0o600)
                snapshot.replace(self.recovery)
            except OSError:
                with self.lock:
                    self.data.update(status='Fehler', error='Modellvergleich nicht gestartet: Ergebnisablage nicht schreibbar')
                return 503, {'error': self.data['error']}
            control.benchmark_active = True
            threading.Thread(target=self.run, args=(selected, original, previous), daemon=True).start()
            return 202, self.status()

    def stop(self):
        if self.controller.benchmark_active:
            self.cancel.set()
            return 202, {'status': 'Abbruch angefordert'}
        return 200, self.status()

    def run(self, models, original, previous):
        control, results = self.controller, list(self.data.get("results", []))
        failed = ''
        try:
            for model in models:
                if self.cancel.is_set():
                    break
                self.publish(current=model, phase='lädt')
                row = {'model': model, 'error': '', 'load_s': None, 'ttft_s': None,
                       'total_s': None, 'tokens_s': None, 'vram_idle_mib': None, 'vram_peak_mib': None}
                try:
                    row['settings'] = control.settings(model)
                    row['voice'] = control.voice(model)
                    started = time.monotonic()
                    control.change(model)
                    if control.state != 'bereit' or control.status()['active'] != model:
                        raise RuntimeError(control.error or 'Modell nicht geladen')
                    row['load_s'] = round(time.monotonic() - started, 2)
                    row['context_tokens'] = control.props().get('default_generation_settings', {}).get('n_ctx')
                    peak, sampler_stop = [gpu_memory()['used_mib']], threading.Event()
                    def sample():
                        while not sampler_stop.wait(0.1):
                            try:
                                peak[0] = max(peak[0], gpu_memory()['used_mib'])
                            except (OSError, ValueError, RuntimeError):
                                pass
                    sampler = threading.Thread(target=sample, daemon=True)
                    sampler.start()
                    def request_sample():
                        if Path(control.props()['model_path']).name != model:
                            raise RuntimeError('Modell wurde außerhalb des Vergleichs gewechselt')
                        result = measure(self.cancel)
                        if Path(control.props()['model_path']).name != model:
                            raise RuntimeError('Modell wurde außerhalb des Vergleichs gewechselt')
                        return result
                    try:
                        self.publish(phase='wärmt auf')
                        for _ in range(2):
                            request_sample()
                        row['vram_idle_mib'] = gpu_memory()['used_mib']
                        samples = []
                        for index in range(3):
                            self.publish(phase=f'misst {index + 1}/3')
                            samples.append(request_sample())
                        row['samples'] = samples
                        for key in ('ttft_s', 'total_s', 'tokens_s'):
                            values = [s[key] for s in samples if s[key] is not None]
                            row[key] = round(statistics.median(values), 3) if values else None
                        row['vram_total_mib'] = gpu_memory()['total_mib']
                    finally:
                        sampler_stop.set()
                        sampler.join(timeout=2)
                        row['vram_peak_mib'] = peak[0]
                except InterruptedError:
                    row['error'] = 'Abgebrochen'
                except Exception as error:
                    row['error'] = 'Abgebrochen' if self.cancel.is_set() else str(error)[:180]
                results.append(row)
                self.publish(results=results, completed=len(results))
                if self.cancel.is_set():
                    break
        except Exception as error:
            failed = str(error)[:180]
        finally:
            with control.lock:
                control.state, control.requested = 'stellt wieder her', original
            # Die Wiederherstellung darf nicht von schreibbarer Ergebnisablage abhängen.
            try:
                self.publish(status='stellt wieder her', phase='stellt wieder her', current=original)
            except OSError:
                failed = 'Ergebnisdatei konnte nicht gespeichert werden'
            restored = False
            try:
                if previous is None:
                    control.dropin.unlink(missing_ok=True)
                else:
                    control.dropin.write_bytes(previous)
                control.systemctl('daemon-reload')
                control.prepare_services(original)
                control.systemctl('restart', 'llama-server.service')
                control.wait_ready(original)
                control.state, control.error, control.requested = 'bereit', '', original
                restored = True
                self.recovery.unlink(missing_ok=True)
            except Exception:
                failed = 'Ursprüngliche Einstellungen übernommen, aber Modell wurde nicht bereit; llama-server prüfen'
            with control.lock:
                control.benchmark_active = False
            status = 'Fehler' if failed else ('abgebrochen' if self.cancel.is_set() else
                     ('fertig mit Fehlern' if any(r['error'] for r in results) else 'fertig'))
            final = {'status': status, 'error': failed, 'restored': restored,
                     'finished': datetime.now().astimezone().isoformat(timespec='seconds')}
            try:
                self.publish(**final)
            except OSError:
                with self.lock:
                    self.data.update(final, error='Ergebnisdatei konnte nicht gespeichert werden')
