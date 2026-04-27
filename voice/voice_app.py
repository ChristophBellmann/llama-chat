#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import requests
import sounddevice as sd

ROOT_DIR = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT_DIR / "voice"

VOICE_MAP = {
    "de_DE-thorsten-medium": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "de_DE-thorsten-high": "de/de_DE/thorsten/high/de_DE-thorsten-high",
    "de_DE-thorsten-low": "de/de_DE/thorsten/low/de_DE-thorsten-low",
    "de_DE-ramona-low": "de/de_DE/ramona/low/de_DE-ramona-low",
}


def find_piper_bin() -> str:
    explicit = os.environ.get("PIPER_BIN", "").strip()
    if explicit:
        return explicit
    found = shutil.which("piper")
    if found:
        return found
    raise FileNotFoundError("piper executable nicht gefunden. Erst ./voice/run.sh setup ausführen.")


def find_piper_model() -> tuple[Path, Optional[Path]]:
    explicit = os.environ.get("PIPER_MODEL", "").strip()
    if explicit:
        model = Path(explicit)
    else:
        model_dir = Path(os.environ.get("PIPER_MODEL_DIR", str(VOICE_DIR / "models" / "piper")))
        preferred = model_dir / "de" / "de_DE" / "thorsten" / "medium" / "de_DE-thorsten-medium.onnx"
        if preferred.exists():
            model = preferred
        else:
            matches = sorted(model_dir.rglob("*.onnx"))
            if not matches:
                raise FileNotFoundError("Kein Piper-Modell gefunden. Erst ./voice/run.sh download-piper ausführen.")
            model = matches[-1]

    config_env = os.environ.get("PIPER_CONFIG", "").strip()
    config = Path(config_env) if config_env else Path(str(model) + ".json")
    return model, config if config.exists() else None


def read_wav(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as wav:
        sr = wav.getframerate()
        channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sampwidth == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {sampwidth}")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return sr, np.clip(audio.astype(np.float32), -1.0, 1.0)


def synthesize_piper(text: str) -> tuple[int, np.ndarray]:
    text = text.strip()
    if not text:
        return 24000, np.zeros(0, dtype=np.float32)

    piper = find_piper_bin()
    model, config = find_piper_model()

    with tempfile.NamedTemporaryFile(prefix="piper_", suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    cmd = [piper, "--model", str(model), "--output_file", str(wav_path)]
    if config is not None:
        cmd.extend(["--config", str(config)])

    proc = subprocess.run(cmd, input=text + "\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        wav_path.unlink(missing_ok=True)
        raise RuntimeError(f"piper failed exit={proc.returncode}\n{proc.stderr}")

    try:
        return read_wav(wav_path)
    finally:
        wav_path.unlink(missing_ok=True)


def play_audio(sr: int, audio: np.ndarray) -> None:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return
    sd.play(audio, samplerate=sr, blocking=True)


def cmd_download_piper(args: argparse.Namespace) -> int:
    from huggingface_hub import hf_hub_download

    voice = args.voice or os.environ.get("PIPER_VOICE", "de_DE-thorsten-medium")
    if voice not in VOICE_MAP:
        known = ", ".join(sorted(VOICE_MAP))
        raise SystemExit(f"Unbekannte Stimme: {voice}\nBekannt: {known}")

    model_dir = Path(os.environ.get("PIPER_MODEL_DIR", str(VOICE_DIR / "models" / "piper")))
    model_dir.mkdir(parents=True, exist_ok=True)
    stem = VOICE_MAP[voice]

    repo = "rhasspy/piper-voices"
    onnx = hf_hub_download(repo_id=repo, filename=f"{stem}.onnx", local_dir=model_dir)
    cfg = hf_hub_download(repo_id=repo, filename=f"{stem}.onnx.json", local_dir=model_dir)

    print(f"PIPER_MODEL={onnx}")
    print(f"PIPER_CONFIG={cfg}")
    return 0


def cmd_tts(args: argparse.Namespace) -> int:
    text = " ".join(args.text).strip() or "Die Haustür ist noch offen."
    t0 = time.perf_counter()
    sr, audio = synthesize_piper(text)
    print(f"Piper: {len(audio)/sr:.2f}s Audio, sr={sr}, synth={time.perf_counter()-t0:.2f}s", flush=True)
    play_audio(sr, audio)
    return 0


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float32))) + 1e-12)) if x.size else 0.0


def record_utterance(
    sample_rate: int = 16000,
    block_s: float = 0.05,
    start_rms: float = 0.018,
    stop_rms: float = 0.010,
    silence_s: float = 0.65,
    max_s: float = 12.0,
) -> np.ndarray:
    block = int(sample_rate * block_s)
    q: queue.Queue[np.ndarray] = queue.Queue()

    def cb(indata, frames, time_info, status):
        q.put(indata[:, 0].copy())

    print("Warte auf Sprache...", flush=True)
    chunks: list[np.ndarray] = []
    active = False
    silence_blocks = 0
    stop_blocks = int(silence_s / block_s)
    max_blocks = int(max_s / block_s)

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", blocksize=block, callback=cb):
        for _ in range(max_blocks):
            x = q.get()
            level = rms(x)

            if not active:
                if level >= start_rms:
                    active = True
                    chunks.append(x)
                    print("Sprache erkannt.", flush=True)
                continue

            chunks.append(x)
            if level < stop_rms:
                silence_blocks += 1
                if silence_blocks >= stop_blocks:
                    break
            else:
                silence_blocks = 0

    return np.concatenate(chunks).astype(np.float32) if chunks else np.zeros(0, dtype=np.float32)


def load_whisper():
    from faster_whisper import WhisperModel

    name = os.environ.get("WHISPER_MODEL", "tiny")
    device = os.environ.get("WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    print(f"Lade Whisper: {name} ({device}, {compute_type})", flush=True)
    return WhisperModel(name, device=device, compute_type=compute_type)


def transcribe(whisper, audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""
    segments, _ = whisper.transcribe(audio, language="de", beam_size=1, vad_filter=False)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _strip_model_markup(text: str) -> str:
    text = (text or "").strip()

    # Wenn nur ein <think>-Block kam, NICHT komplett leer machen,
    # sondern den Text später als Debug/Fallback sichtbar lassen.
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()

    for marker in [
        "<|im_end|>",
        "<|endoftext|>",
        "<|eot_id|>",
        "</s>",
        "<think>",
        "</think>",
    ]:
        text = text.replace(marker, "")

    return text.strip()


def _extract_llm_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""

    c = choices[0]

    candidates = []

    # OpenAI chat format
    msg = c.get("message")
    if isinstance(msg, dict):
        for key in [
            "content",
            "reasoning_content",
            "reasoning",
            "thoughts",
        ]:
            val = msg.get(key)
            if val:
                candidates.append(val)

    # Completion / alternative llama.cpp formats
    for key in [
        "content",
        "text",
        "response",
        "reasoning_content",
        "reasoning",
    ]:
        val = c.get(key)
        if val:
            candidates.append(val)

    for val in candidates:
        if isinstance(val, list):
            val = " ".join(
                str(x.get("text", x)) if isinstance(x, dict) else str(x)
                for x in val
            )

        txt = _strip_model_markup(str(val))
        if txt:
            return txt

    return ""


def _strip_model_markup(text: str) -> str:
    text = (text or "").strip()

    # Sichtbaren Anteil nach einem Think-Block bevorzugen.
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()

    for marker in [
        "<|im_end|>",
        "<|endoftext|>",
        "<|eot_id|>",
        "</s>",
        "<think>",
        "</think>",
    ]:
        text = text.replace(marker, "")

    return text.strip()


def _extract_llm_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""

    c = choices[0]
    msg = c.get("message") or {}

    # 1. Normale sichtbare Antwort bevorzugen.
    content = msg.get("content") or c.get("text") or c.get("content") or ""
    if isinstance(content, list):
        content = " ".join(
            str(x.get("text", x)) if isinstance(x, dict) else str(x)
            for x in content
        )

    text = _strip_model_markup(str(content))
    if text:
        return text

    # 2. Reasoning NICHT als Antwort verwenden.
    # Wenn nur reasoning_content existiert, war das Tokenbudget zu klein
    # oder Thinking wurde nicht deaktiviert.
    return ""


def reply_llama(text: str) -> str:
    import json
    from pathlib import Path

    url = os.environ.get(
        "LLAMA_API_URL",
        "http://127.0.0.1:8080/v1/chat/completions",
    )
    model = os.environ.get("LLAMA_MODEL", "qwen-local")

    clean = text.strip()
    user_text = f"/no_think\n{clean}\n/no_think"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "/no_think\n"
                    "Antworte direkt auf Deutsch mit genau einem kurzen Satz. "
                    "Kein Markdown. Kein Denken. Kein <think>. "
                    "Gib nur die Antwort aus, die vorgelesen werden soll."
                ),
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        "temperature": float(os.environ.get("LLAMA_TEMP", "0.3")),
        "top_p": float(os.environ.get("LLAMA_TOP_P", "0.9")),

        # Wichtig: Thinking-Modelle brauchen sonst das ganze Budget im reasoning_content.
        "max_tokens": int(os.environ.get("LLAMA_MAX_TOKENS", "512")),
        "stream": False,

        # Wird von manchen llama.cpp/Qwen-Templates beachtet, von manchen Builds ignoriert.
        "chat_template_kwargs": {
            "enable_thinking": False,
        },
    }

    r = requests.post(
        url,
        json=payload,
        timeout=int(os.environ.get("LLAMA_TIMEOUT", "120")),
    )
    r.raise_for_status()
    data = r.json()

    Path("/tmp/voice_last_llm_response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )

    answer = _extract_llm_text(data)

    if os.environ.get("VOICE_DEBUG_LLM", "0") == "1":
        print("LLM RAW saved: /tmp/voice_last_llm_response.json", flush=True)
        print("LLM parsed repr:", repr(answer), flush=True)

    if not answer:
        finish = ""
        try:
            finish = data["choices"][0].get("finish_reason", "")
        except Exception:
            pass

        if finish == "length":
            return "Die Antwort war zu lang zum Verarbeiten."

        return "Ich habe gerade keine verwertbare Antwort erhalten."

    answer = answer.splitlines()[0].strip()
    return answer[:500]

def make_reply(mode: str, text: str) -> str:
    if mode == "echo":
        return text
    if mode == "static":
        return "Ich habe dich verstanden."
    if mode == "llama":
        return reply_llama(text)
    raise ValueError(mode)


def cmd_loop(args: argparse.Namespace) -> int:
    whisper = load_whisper()
    print("Voice Loop bereit. Abbruch mit Ctrl+C.", flush=True)

    while True:
        try:
            audio = record_utterance(
                start_rms=float(os.environ.get("VOICE_START_RMS", "0.018")),
                stop_rms=float(os.environ.get("VOICE_STOP_RMS", "0.010")),
                silence_s=float(os.environ.get("VOICE_SILENCE_S", "0.65")),
                max_s=float(os.environ.get("VOICE_MAX_S", "12")),
            )
            text = transcribe(whisper, audio)
            if not text:
                continue
            print(f"Du: {text}", flush=True)
            answer = make_reply(args.reply, text)
            print(f"Antwort: {answer}", flush=True)
            sr, out = synthesize_piper(answer)
            play_audio(sr, out)
        except KeyboardInterrupt:
            print("\nBeendet.", flush=True)
            return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    import importlib

    for mod in ["numpy", "sounddevice", "faster_whisper", "requests", "huggingface_hub"]:
        importlib.import_module(mod)
        print(f"OK import {mod}")
    print("piper executable:", shutil.which("piper"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Minimal voice pipeline: Whisper -> reply -> Piper")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download-piper")
    d.add_argument("voice", nargs="?", help="Default: de_DE-thorsten-medium")
    d.set_defaults(func=cmd_download_piper)

    t = sub.add_parser("tts")
    t.add_argument("text", nargs="*")
    t.set_defaults(func=cmd_tts)

    l = sub.add_parser("loop")
    l.add_argument("--reply", choices=["echo", "static", "llama"], default="echo")
    l.set_defaults(func=cmd_loop)

    s = sub.add_parser("smoke")
    s.set_defaults(func=cmd_smoke)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
