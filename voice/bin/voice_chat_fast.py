#!/usr/bin/env python3
import json
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

try:
    import yaml
except Exception:
    print("Fehler: PyYAML fehlt. Installiere mit: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)


def load_cfg(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("voice/config.yaml ist ungueltig (kein Mapping).")
    return cfg


def http_json(url, payload, timeout_sec):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def http_multipart(url, fields, file_field, filename, file_bytes, content_type, timeout_sec):
    boundary = f"----codex-{uuid.uuid4().hex}"
    body = bytearray()
    for k, v in fields.items():
        if v is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(v).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(
            "utf-8"
        )
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    return raw, ctype


def _wait_for_enter(timeout_sec):
    ready, _, _ = select.select([sys.stdin], [], [], timeout_sec)
    if ready:
        sys.stdin.readline()
        return True
    return False


def record_audio_bytes(audio_cfg):
    backend = str(audio_cfg.get("backend", "pipewire")).strip().lower()
    sample_rate = int(audio_cfg.get("sample_rate", 16000))
    channels = int(audio_cfg.get("channels", 1))
    max_record_seconds = int(audio_cfg.get("max_record_seconds", 12))
    input_device = str(audio_cfg.get("input_device", "")).strip()

    if backend == "pipewire":
        cmd = ["pw-record", "--rate", str(sample_rate), "--channels", str(channels)]
        if input_device:
            cmd.extend(["--target", input_device])
        cmd.append("-")
    elif backend == "alsa":
        alsa_dev = input_device or "default"
        cmd = [
            "arecord",
            "-q",
            "-D",
            alsa_dev,
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-t",
            "wav",
            "-",
        ]
    else:
        raise RuntimeError(f"audio.backend muss 'pipewire' oder 'alsa' sein (aktuell: {backend})")

    print("Enter = start recording")
    sys.stdin.readline()
    print(f"Enter = stop recording (Auto-Stop nach {max_record_seconds}s)")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _wait_for_enter(max_record_seconds)
    if proc.poll() is None:
        proc.terminate()
    try:
        out, err = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=2)
    if proc.returncode not in (0, -15, -2):
        raise RuntimeError(f"Aufnahme fehlgeschlagen ({proc.returncode}): {err.decode('utf-8', errors='ignore')}")
    if not out or len(out) < 128:
        return b""
    return out


def stt_whisper_server(audio_wav_bytes, stt_cfg):
    server_url = str(stt_cfg.get("server_url", "http://127.0.0.1:8081/inference")).strip()
    timeout = int(stt_cfg.get("request_timeout_sec", 30))
    lang = str(stt_cfg.get("lang", "de")).strip()
    file_field = str(stt_cfg.get("file_field", "file")).strip() or "file"
    text_key = str(stt_cfg.get("response_text_key", "text")).strip() or "text"
    lang_field = str(stt_cfg.get("language_field", "language")).strip() or "language"

    fields = {lang_field: lang} if lang else {}
    raw, ctype = http_multipart(
        server_url,
        fields=fields,
        file_field=file_field,
        filename="in.wav",
        file_bytes=audio_wav_bytes,
        content_type="audio/wav",
        timeout_sec=timeout,
    )

    ctype_l = (ctype or "").lower()
    if "application/json" in ctype_l or raw.lstrip().startswith(b"{"):
        data = json.loads(raw.decode("utf-8"))
        txt = data.get(text_key)
        if txt is None:
            txt = data.get("transcript", "")
        return str(txt or "").strip()
    return raw.decode("utf-8", errors="ignore").strip()


def llm_llama_server(transcript, llm_cfg, prompt_cfg):
    base_url = str(llm_cfg.get("base_url", "http://127.0.0.1:8080/v1")).strip()
    if base_url.endswith("/v1"):
        url = f"{base_url}/chat/completions"
    else:
        url = f"{base_url}/v1/chat/completions"

    payload = {
        "model": str(llm_cfg.get("model_alias", "qwen-local")),
        "messages": [
            {"role": "system", "content": str(prompt_cfg.get("system", ""))},
            {"role": "user", "content": transcript},
        ],
        "temperature": float(llm_cfg.get("temperature", 0.7)),
        "top_p": float(llm_cfg.get("top_p", 0.9)),
        "max_tokens": int(llm_cfg.get("max_tokens", 400)),
    }
    timeout = int(llm_cfg.get("request_timeout_sec", 120))
    data = http_json(url, payload, timeout_sec=timeout)
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return str(msg.get("content") or "").strip()


def tts_orpheus(response_text, tts_cfg):
    base_url = str(tts_cfg.get("base_url", "http://127.0.0.1:5005/v1")).strip()
    if base_url.endswith("/v1"):
        url = f"{base_url}/audio/speech"
    else:
        url = f"{base_url}/v1/audio/speech"
    timeout = int(tts_cfg.get("request_timeout_sec", 120))
    payload = {
        "model": str(tts_cfg.get("model", "orpheus")),
        "voice": str(tts_cfg.get("voice", "tara")),
        "input": response_text,
        "format": str(tts_cfg.get("format", "wav")),
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"TTS HTTP {e.code}: {detail}") from e

    if "application/json" in ctype or raw.lstrip().startswith(b"{"):
        data = json.loads(raw.decode("utf-8"))
        # OpenAI-compatible TTS endpoints return binary; JSON fallback is kept for custom gateways.
        b64_audio = data.get("audio")
        if isinstance(b64_audio, str):
            import base64

            return base64.b64decode(b64_audio)
        raise RuntimeError("TTS JSON-Antwort ohne Audio-Inhalt.")
    return raw


def play_audio_bytes(wav_bytes, audio_cfg):
    backend = str(audio_cfg.get("backend", "pipewire")).strip().lower()
    output_device = str(audio_cfg.get("output_device", "")).strip()
    if backend == "pipewire":
        cmd = ["pw-play"]
        if output_device:
            cmd.extend(["--target", output_device])
        cmd.append("-")
    elif backend == "alsa":
        alsa_dev = output_device or "default"
        cmd = ["aplay", "-q", "-D", alsa_dev]
    else:
        raise RuntimeError(f"audio.backend muss 'pipewire' oder 'alsa' sein (aktuell: {backend})")
    proc = subprocess.run(cmd, input=wav_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore") or "Playback fehlgeschlagen.")


def append_log(log_file, user_text, assistant_text):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] USER: {user_text}\n")
        f.write(f"[{ts}] ASSISTANT: {assistant_text}\n\n")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    config_path = os.path.join(repo_root, "voice", "config.yaml")
    runtime_dir = os.path.join(repo_root, "voice", "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    log_file = os.path.join(runtime_dir, "voice.log")

    cfg = load_cfg(config_path)
    audio_cfg = cfg.get("audio", {}) if isinstance(cfg.get("audio", {}), dict) else {}
    stt_cfg = cfg.get("stt", {}) if isinstance(cfg.get("stt", {}), dict) else {}
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
    tts_cfg = cfg.get("tts", {}) if isinstance(cfg.get("tts", {}), dict) else {}
    prompt_cfg = cfg.get("prompts", {}) if isinstance(cfg.get("prompts", {}), dict) else {}

    stt_backend = str(stt_cfg.get("backend", "whisper_server")).strip().lower()
    tts_backend = str(tts_cfg.get("backend", "orpheus_server")).strip().lower()

    print("Voice-Loop gestartet (fast path).")
    print("[Enter] = neue Aufnahme, /q = beenden")

    while True:
        print("voice> ", end="", flush=True)
        cmd = sys.stdin.readline()
        if not cmd:
            break
        if cmd.strip() == "/q":
            print("Beendet durch User-Command.")
            break

        try:
            audio_wav = record_audio_bytes(audio_cfg)
            if not audio_wav:
                print("Leere Aufnahme, naechster Durchlauf.")
                continue

            if stt_backend == "whisper_server":
                transcript = stt_whisper_server(audio_wav, stt_cfg)
            else:
                raise RuntimeError(
                    f"Unbekanntes stt.backend='{stt_backend}' (erlaubt: whisper_server)"
                )
            transcript = transcript.strip()
            if not transcript:
                print("Leere Transkription, naechster Durchlauf.")
                continue
            print(f"STT: {transcript}")
            if "/q" in transcript:
                print("Abbruchkommando in Transkript erkannt.")
                break

            response = llm_llama_server(transcript, llm_cfg, prompt_cfg)
            print(f"ASSISTANT: {response}")

            if tts_backend == "orpheus_server":
                wav_out = tts_orpheus(response, tts_cfg)
            else:
                raise RuntimeError(
                    f"Unbekanntes tts.backend='{tts_backend}' (erlaubt: orpheus_server)"
                )
            if wav_out:
                play_audio_bytes(wav_out, audio_cfg)
            append_log(log_file, transcript, response)
        except Exception as exc:
            print(f"Fehler: {exc}", file=sys.stderr)

    print("Voice-Loop beendet.")


if __name__ == "__main__":
    main()
