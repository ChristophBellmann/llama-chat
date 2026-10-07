#!/usr/bin/env python3
"""Measure model profiles with Orpheus resident on GPU; restore the active model.

Run with voice/.venv/bin/python3. This temporarily restarts llama-server and
pauses workstation-power to prevent competing HA model switches or suspend.
"""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    'GPU_LAYERS': 'auto', 'CTX': 8192, 'PARALLEL': 1,
    'BATCH_SIZE': 512, 'UBATCH_SIZE': 256,
    'CACHE_TYPE_K': 'q8_0', 'CACHE_TYPE_V': 'q8_0',
    'LLAMA_ARG_FIT': 'on', 'LLAMA_ARG_FIT_TARGET': 2048,
    'GGML_CUDA_DISABLE_GRAPHS': 1, 'LLAMA_ARG_LOG_VERBOSITY': 4,
}
DROPIN = Path.home() / '.config/systemd/user/llama-server.service.d/zzz-tuning.conf'
GPU = next(iter(sorted(Path('/sys/class/drm').glob('card*/device/mem_info_vram_used'))))
PROMPT = ('Antworte kurz und sachlich auf Deutsch.\n' +
          'Die Heizung nutzt eine Wärmepumpe. Das Haus hat gut gedämmte Fenster. ' * 80 +
          '\nErkläre in vier kurzen Sätzen, wie eine Wärmepumpe ein Haus heizt.')


def systemctl(*args, timeout=35):
    return subprocess.run(['systemctl', '--user', *args], check=True,
                          capture_output=True, text=True, timeout=timeout).stdout.strip()


def api(path, body=None, port=8080, timeout=90):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/{path}',
                                    data=json.dumps(body).encode() if body is not None else None,
                                    headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_ready(model, timeout=180):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            if api('health', timeout=2).get('status') == 'ok' and Path(api('props', timeout=2)['model_path']).name == model:
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f'Model did not become ready: {model}')


def restart():
    systemctl('daemon-reload')
    try:
        systemctl('restart', 'llama-server')
    except subprocess.TimeoutExpired:
        # The previous graph may be stuck. Kill only the already stopping service.
        subprocess.run(['systemctl', '--user', 'kill', '--kill-whom=main',
                        '--signal=SIGKILL', 'llama-server'], capture_output=True)
        systemctl('start', 'llama-server')


def load(model, settings):
    lines = ['[Service]', f'Environment="MODEL_PATH={ROOT / "models" / model}"']
    lines += [f'Environment="{key}={value}"' for key, value in settings.items()]
    DROPIN.write_text('\n'.join(lines) + '\n')
    started = time.monotonic()
    restart()
    wait_ready(model)
    return round(time.monotonic() - started, 2)


def memory():
    pid = int(systemctl('show', 'llama-server', '-p', 'MainPID', '--value'))
    status = Path(f'/proc/{pid}/status').read_text()
    vram = evicted = 0
    clients = set()
    for path in Path(f'/proc/{pid}/fdinfo').iterdir():
        data = path.read_text()
        client = re.search(r'drm-client-id:\s*(\d+)', data)
        if not client or client[1] in clients:
            continue
        clients.add(client[1])
        for label in ['drm-memory-vram', 'amd-evicted-vram']:
            match = re.search(label + r':\s*(\d+)', data)
            if match:
                if label == 'drm-memory-vram':
                    vram += int(match[1])
                else:
                    evicted += int(match[1])
    meminfo = Path('/proc/meminfo').read_text()
    return {'process_vram_mib': round(vram / 1024, 1),
            'total_vram_mib': round(int(GPU.read_text()) / 1024**2, 1),
            'capacity_mib': round(int(GPU.with_name('mem_info_vram_total').read_text()) / 1024**2, 1),
            'rss_mib': round(int(re.search(r'VmRSS:\s*(\d+)', status)[1]) / 1024, 1),
            'process_swap_mib': round(int(re.search(r'VmSwap:\s*(\d+)', status)[1]) / 1024, 1),
            'available_ram_mib': round(int(re.search(r'MemAvailable:\s*(\d+)', meminfo)[1]) / 1024, 1),
            'evicted_vram_mib': round(evicted / 1024, 1)}


def log_info():
    pid = systemctl('show', 'llama-server', '-p', 'MainPID', '--value')
    logs = subprocess.check_output(['journalctl', '--user', f'_PID={pid}', '--no-pager'], text=True)
    layers = re.search(r'offloaded (\d+)/(\d+) layers', logs)
    kv = re.findall(r'ROCm0 KV buffer size\s*=\s*([\d.]+) MiB', logs)
    cpu = re.findall(r'CPU(?:_Mapped)? model buffer size\s*=\s*([\d.]+) MiB', logs)
    return {'gpu_layers': int(layers[1]) if layers else None,
            'total_layers': int(layers[2]) if layers else None,
            'kv_gpu_mib': sum(map(float, kv)), 'cpu_model_buffer_mib': sum(map(float, cpu)),
            'cpu_tensor_overrides': 'tensor overrides to CPU' in logs}


def chat(prompt=PROMPT, tokens=64):
    started = time.monotonic()
    response = api('v1/chat/completions', {'model': 'locales_llm',
        'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0,
        'seed': 42, 'max_tokens': tokens, 'cache_prompt': False})
    answer = response['choices'][0]['message'].get('content') or ''
    if not answer.strip():
        raise RuntimeError('Empty text response')
    return {'seconds': round(time.monotonic() - started, 3), 'answer': answer,
            'timings': response.get('timings', {}), 'usage': response.get('usage', {})}


def tts():
    import voice_app
    started = time.monotonic()
    first, duration = None, 0
    for sr, chunk in voice_app.stream_orpheus_audio('Hallo Christoph. Das Licht im Wohnzimmer ist eingeschaltet.'):
        if first is None:
            first = time.monotonic() - started
        duration += len(chunk) / sr
    elapsed = time.monotonic() - started
    if not duration:
        raise RuntimeError('No Orpheus audio')
    return {'elapsed_s': round(elapsed, 3), 'audio_s': round(duration, 3),
            'rtf': round(elapsed / duration, 3), 'first_audio_s': round(first, 3)}


def measure(model, settings):
    load_s = load(model, settings)
    before = memory()
    info = log_info()
    peak = [before['total_vram_mib']]
    stop = threading.Event()
    def sample():
        while not stop.wait(0.1):
            peak[0] = max(peak[0], int(GPU.read_text()) / 1024**2)
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        short = chat('Antworte mit einem Wort: Was ist die Hauptstadt von Frankreich?', 12)
        warm = chat()
        measured = chat()
        after = memory()
    finally:
        stop.set()
        sampler.join(timeout=2)
    return {'settings': dict(settings), 'load_s': load_s, 'allocation': info,
            'memory': after, 'peak_total_vram_mib': round(max(peak[0], after['total_vram_mib']), 1),
            'short_chat': short, 'warmup_chat': warm, 'chat': measured}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def model_inventory(names=None):
    sys.path.insert(0, str(ROOT / 'llama.cpp/gguf-py'))
    from gguf import GGUFReader
    rows, seen = [], set()
    base = (ROOT / 'models').resolve()
    for path in sorted(base.glob('*.gguf')):
        path = path.resolve()
        if (path in seen or path.parent != base or
                not re.fullmatch(r'[\w.+ -]+\.gguf', path.name)):
            continue
        seen.add(path)
        if names is not None and path.name not in names:
            continue
        reader = GGUFReader(str(path))
        fields = {key: value.contents() for key, value in reader.fields.items()
                  if key in ['general.architecture', 'general.name'] or key.endswith('.context_length')}
        rows.append({'file': path.name, 'bytes': path.stat().st_size, 'fields': fields})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, help='Optional pre-read GGUF metadata JSON')
    parser.add_argument('--models', nargs='*')
    parser.add_argument('--max-context', type=int, default=65536)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'voice'))
    os.environ.setdefault('SNAC_DEVICE', 'cpu')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('ORPHEUS_TTS_N_PREDICT', '512')
    inventory = json.loads(args.inventory.read_text()) if args.inventory else model_inventory(args.models)
    if args.models and set(args.models) - {row['file'] for row in inventory}:
        raise SystemExit('Some requested models are missing from the inventory.')
    # Restore the tested active model rather than selecting a winner implicitly.
    original = Path(api('props')['model_path']).name
    api('health', port=8082)
    if any(slot.get('is_processing') for port in [8080, 8082] for slot in api('slots', port=port)):
        raise SystemExit('A model is processing a request; retry when idle.')
    power_active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'workstation-power']).returncode == 0
    previous = DROPIN.read_bytes() if DROPIN.exists() else None
    selected = [row for row in inventory if args.models is None or row['file'] in args.models]
    selected.sort(key=lambda row: (row['file'] != 'Qwen3.5-9B-Q4_K_M.gguf', row['bytes']))
    report_path = ROOT / 'profiles/model-measurements.json'
    settings_path = ROOT / 'profiles/model-settings.json'
    report = {'version': 1, 'started': datetime.now().astimezone().isoformat(),
              'status': 'running', 'original_model': original,
              'method': 'Orpheus on GPU, one slot, q8 KV, disabled GPU graphs; ~1500-2000-token prompt, max 64 output tokens; allocation test, not a full-context quality benchmark',
              'results': {}}
    if report_path.exists():
        old = json.loads(report_path.read_text())
        report['results'] = old.get('results', {})
        report['previous_started'] = old.get('started')
    profiles = {'version': 1, 'defaults': DEFAULTS, 'models': {}}
    if settings_path.exists():
        profiles['models'] = json.loads(settings_path.read_text()).get('models', {})
    try:
        if power_active:
            systemctl('stop', 'workstation-power')
        tts()  # Initialize the CPU audio decoder before measuring warm streaming.
        for row in selected:
            model = row['file']
            print(f'MEASURE {model}', flush=True)
            trials = []
            try:
                settings = dict(DEFAULTS)
                trained = next(v for k, v in row['fields'].items() if k.endswith('.context_length'))
                settings['CTX'] = min(8192, trained)
                first = measure(model, settings)
                trials.append(first)
                # HIP's prediction misses some display/runtime allocations. Calibrate
                # the fit target against actual total VRAM after real inference.
                for _ in range(3):
                    mem = first['memory']
                    free = mem['capacity_mib'] - first['peak_total_vram_mib']
                    if free >= 1024:
                        break
                    settings['LLAMA_ARG_FIT_TARGET'] = int(math.ceil(
                        (settings['LLAMA_ARG_FIT_TARGET'] + 1024 - free + 128) / 256) * 256)
                    first = measure(model, settings)
                    trials.append(first)
                if first['memory']['capacity_mib'] - first['peak_total_vram_mib'] < 896:
                    raise RuntimeError('Insufficient measured VRAM reserve after calibration')
                print(json.dumps({'model': model, 'stage': 'baseline', 'memory': first['memory'], 'allocation': first['allocation'], 'chat_timings': first['chat']['timings']}), flush=True)
                # Grow context only when all layers fit. Estimate KV growth and then load/test it.
                info, mem = first['allocation'], first['memory']
                available = mem['capacity_mib'] - first['peak_total_vram_mib'] - 1024 - 128
                limit = min(args.max_context, trained)
                if (info['gpu_layers'] == info['total_layers'] and not info['cpu_tensor_overrides']
                        and info['kv_gpu_mib'] > 0 and available > 0):
                    estimate = settings['CTX'] * (1 + available / info['kv_gpu_mib'])
                    ctx = 2 ** math.floor(math.log2(min(limit, estimate)))
                    while ctx > settings['CTX']:
                        expanded = dict(settings, CTX=ctx)
                        try:
                            trial = measure(model, expanded)
                        except Exception as error:
                            trials.append({'settings': expanded, 'error': str(error)})
                            ctx //= 2
                            continue
                        trials.append(trial)
                        if (trial['allocation']['gpu_layers'] == trial['allocation']['total_layers']
                                and not trial['allocation']['cpu_tensor_overrides']
                                and trial['memory']['capacity_mib'] - trial['peak_total_vram_mib'] >= 896):
                            settings = expanded
                            break
                        else:
                            ctx //= 2
                    if trials[-1].get('settings') != settings:
                        load(model, settings)
                best = next(t for t in reversed(trials) if t['settings'] == settings)
                # Test larger batches only with ample reserve, using the same prompt.
                if best['memory']['capacity_mib'] - best['peak_total_vram_mib'] > 2048:
                    larger = dict(settings, BATCH_SIZE=1024, UBATCH_SIZE=512)
                    try:
                        trial = measure(model, larger)
                        trials.append(trial)
                        a = best['chat']['timings'].get('prompt_per_second', 0)
                        b = trial['chat']['timings'].get('prompt_per_second', 0)
                        if b > a * 1.05 and trial['memory']['capacity_mib'] - trial['peak_total_vram_mib'] >= 896:
                            settings, best = larger, trial
                    except Exception as error:
                        trials.append({'settings': larger, 'error': str(error)})
                    if settings != larger:
                        load(model, settings)
                speech_samples = [tts(), tts()]
                speech = speech_samples[-1]
                final_memory = memory()
                if final_memory['capacity_mib'] - final_memory['total_vram_mib'] < 896:
                    raise RuntimeError('Insufficient VRAM reserve after Orpheus synthesis')
                if final_memory['process_swap_mib'] or final_memory['evicted_vram_mib']:
                    raise RuntimeError('Swap or VRAM eviction detected')
                notes = []
                if (best['allocation']['gpu_layers'] != best['allocation']['total_layers']
                        or best['allocation']['cpu_tensor_overrides']):
                    notes.append('Partial CPU offload is necessary alongside Orpheus; slower than full GPU.')
                if speech['rtf'] > 1.2:
                    notes.append('Orpheus exceeded realtime in this short sample.')
                measurements = {'memory': final_memory, 'allocation': best['allocation'],
                                'chat': best['chat'], 'tts': speech, 'tts_samples': speech_samples}
                profiles['models'][model] = {'settings': settings, 'measurements': measurements, 'notes': notes}
                report['results'][model] = {'trials': trials, 'selected_settings': settings,
                                           'tts': speech, 'tts_samples': speech_samples,
                                           'final_memory': final_memory, 'notes': notes}
                print('RESULT ' + json.dumps({'model': model, 'settings': settings, 'memory': final_memory,
                                             'tts': speech, 'notes': notes}), flush=True)
            except Exception as error:
                report['results'][model] = {'trials': trials, 'error': f'{type(error).__name__}: {error}'}
                print(f'ERROR {model}: {error}', flush=True)
            write_json(report_path, report)
            write_json(settings_path, profiles)
        report['status'] = 'finished'
    finally:
        if previous is None:
            DROPIN.unlink(missing_ok=True)
        else:
            DROPIN.write_bytes(previous)
        try:
            restart()
            wait_ready(original)
            report['restored'] = True
        finally:
            if power_active:
                systemctl('start', 'workstation-power')
            report['finished'] = datetime.now().astimezone().isoformat()
            write_json(report_path, report)
            write_json(settings_path, profiles)


if __name__ == '__main__':
    main()
