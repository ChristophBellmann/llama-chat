#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
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

CUSTOM_RE = re.compile(r"<custom_token_(\d+)>")

_HTTP = requests.Session()
_SNAC_CACHE = {}



# -----------------------------------------------------------------------------
# Audio helpers
# -----------------------------------------------------------------------------


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


def play_audio(sr: int, audio: np.ndarray) -> None:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return
    sd.play(audio, samplerate=sr, blocking=True)


# -----------------------------------------------------------------------------
# Piper TTS
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# Orpheus TTS
# -----------------------------------------------------------------------------


def orpheus_prompt(text: str, voice: Optional[str] = None) -> str:
    voice = voice or os.environ.get("ORPHEUS_VOICE", "jana")
    return (
        f"<custom_token_3><|begin_of_text|>"
        f"{voice}: {text.strip()}"
        f"<|eot_id|><custom_token_4><custom_token_5><custom_token_1>"
    )


def find_orpheus_model() -> str:
    explicit = os.environ.get("ORPHEUS_TTS_MODEL", "").strip() or os.environ.get("ORPHEUS_MODEL", "").strip()
    if explicit:
        return explicit

    base = Path(os.environ.get("HF_HUB_CACHE", ROOT_DIR / ".cache" / "huggingface" / "hub"))
    matches = sorted(
        base.glob(
            "models--freddyaboulton--3b-de-ft-research_release-Q4_K_M-GGUF"
            "/snapshots/*/3b-de-ft-research_release-q4_k_m.gguf"
        )
    )
    if matches:
        return str(matches[-1])

    local = VOICE_DIR / "models" / "orpheus" / "3b-de-ft-research_release-q4_k_m.gguf"
    if local.exists():
        return str(local)

    raise FileNotFoundError("Orpheus-DE GGUF nicht gefunden. Erst ./voice/run.sh download-orpheus ausführen.")


def custom_token_to_code(token_text: str, index: int) -> Optional[int]:
    m = CUSTOM_RE.search(token_text)
    if not m:
        return None
    raw = int(m.group(1))
    code = raw - 10 - ((index % 7) * 4096)
    if code < 0 or code > 4095:
        return None
    return code


def extract_custom_tokens(text: str) -> list[str]:
    return CUSTOM_RE.findall(text)


def token_text_to_codes(text: str) -> list[int]:
    codes: list[int] = []
    for idx, m in enumerate(CUSTOM_RE.finditer(text)):
        code = custom_token_to_code(m.group(0), idx)
        if code is not None:
            codes.append(code)
    return codes


def _get_snac_model(device: str):
    cached = _SNAC_CACHE.get(device)
    if cached is not None:
        return cached

    import torch
    from snac import SNAC

    model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to(device)
    _SNAC_CACHE[device] = (torch, model)
    return torch, model


def decode_snac_codes(codes: list[int]) -> tuple[int, np.ndarray]:
    # Orpheus/SNAC uses groups of 7 tokens per frame.
    n = (len(codes) // 7) * 7
    codes = codes[:n]
    if n < 28:
        raise RuntimeError(f"Zu wenige Orpheus-Audiotokens: {len(codes)}")

    max_codes = int(os.environ.get("ORPHEUS_MAX_CODES", "1400"))
    if len(codes) > max_codes:
        codes = codes[: (max_codes // 7) * 7]

    # Fast/stable default: keep SNAC on CPU. Orpheus token server may use GPU.
    device = os.environ.get("SNAC_DEVICE", "cpu").strip() or "cpu"
    torch, model = _get_snac_model(device)

    c0: list[int] = []
    c1: list[int] = []
    c2: list[int] = []

    frames = len(codes) // 7
    for j in range(frames):
        i = 7 * j
        c0.append(codes[i])
        c1.extend([codes[i + 1], codes[i + 4]])
        c2.extend([codes[i + 2], codes[i + 3], codes[i + 5], codes[i + 6]])

    tensors = [
        torch.tensor(c0, device=device, dtype=torch.int32).unsqueeze(0),
        torch.tensor(c1, device=device, dtype=torch.int32).unsqueeze(0),
        torch.tensor(c2, device=device, dtype=torch.int32).unsqueeze(0),
    ]

    for t in tensors:
        if torch.any(t < 0) or torch.any(t > 4095):
            raise RuntimeError("SNAC code außerhalb 0..4095")

    with torch.inference_mode():
        audio_hat = model.decode(tensors)

    audio = audio_hat.detach().cpu().numpy().reshape(-1).astype(np.float32)
    return 24000, np.clip(audio, -1.0, 1.0)


def generate_orpheus_tokens_cli(text: str) -> str:
    model = find_orpheus_model()
    llama_completion = ROOT_DIR / "llama.cpp" / "build" / "bin" / "llama-completion"
    if not llama_completion.exists():
        raise FileNotFoundError(f"llama-completion nicht gefunden: {llama_completion}")

    cmd = [
        str(llama_completion),
        "--log-disable",
        "--model", model,
        "--prompt", orpheus_prompt(text),
        "--ctx-size", os.environ.get("ORPHEUS_TTS_CTX", "2048"),
        "--threads", os.environ.get("ORPHEUS_TTS_THREADS", "6"),
        "--gpu-layers", os.environ.get("ORPHEUS_TTS_GPU_LAYERS", "0"),
        "--n-predict", os.environ.get("ORPHEUS_TTS_N_PREDICT", "600"),
        "--temp", os.environ.get("ORPHEUS_TTS_TEMP", "0.6"),
        "--top-p", os.environ.get("ORPHEUS_TTS_TOP_P", "0.9"),
        "--repeat-penalty", os.environ.get("ORPHEUS_TTS_REPEAT_PENALTY", "1.1"),
        "--batch-size", os.environ.get("ORPHEUS_TTS_BATCH", "8"),
        "--ubatch-size", os.environ.get("ORPHEUS_TTS_UBATCH", "4"),
        "--no-display-prompt",
        "--simple-io",
        "--color", "off",
        "--special",
        "--ignore-eos",
        "-no-cnv",
        "--no-warmup",
        "--flash-attn", "off",
    ]

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = f"{ROOT_DIR}/llama.cpp/build/bin:{env.get('LD_LIBRARY_PATH', '')}"

    if os.environ.get("ORPHEUS_VERBOSE", "0") == "1":
        print("orpheus-cli:", " ".join(cmd), flush=True)

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(os.environ.get("ORPHEUS_TTS_TIMEOUT", "240")),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"orpheus llama-completion failed exit={proc.returncode}\n{proc.stderr}")
    return proc.stdout


def generate_orpheus_tokens_server(text: str) -> str:
    url = os.environ.get("ORPHEUS_COMPLETION_URL", "http://127.0.0.1:8082/completion")
    payload = {
        "prompt": orpheus_prompt(text),
        "n_predict": int(os.environ.get("ORPHEUS_TTS_N_PREDICT", "600")),
        "temperature": float(os.environ.get("ORPHEUS_TTS_TEMP", "0.6")),
        "top_p": float(os.environ.get("ORPHEUS_TTS_TOP_P", "0.9")),
        "repeat_penalty": float(os.environ.get("ORPHEUS_TTS_REPEAT_PENALTY", "1.1")),
        "stream": False,
        "cache_prompt": False,
        "special": True,
        "ignore_eos": True,
    }
    r = _HTTP.post(url, json=payload, timeout=int(os.environ.get("ORPHEUS_TTS_TIMEOUT", "240")))
    if os.environ.get("ORPHEUS_VERBOSE", "0") == "1":
        print("orpheus-server HTTP:", r.status_code, flush=True)
        print(r.text[:1000], flush=True)
    r.raise_for_status()
    data = r.json()

    for key in ["content", "text", "response", "completion"]:
        val = data.get(key)
        if isinstance(val, str) and val:
            return val

    # OpenAI-like fallback, just in case.
    choices = data.get("choices") or []
    if choices:
        c = choices[0]
        if isinstance(c.get("text"), str):
            return c["text"]
        msg = c.get("message") or {}
        if isinstance(msg.get("content"), str):
            return msg["content"]

    raise RuntimeError(f"Keine Token-Ausgabe in Orpheus-Server-Antwort: {list(data.keys())}")


def synthesize_orpheus(text: str, mode: str = "cli") -> tuple[int, np.ndarray]:
    if mode == "server":
        token_text = generate_orpheus_tokens_server(text)
    elif mode == "cli":
        token_text = generate_orpheus_tokens_cli(text)
    else:
        raise ValueError(mode)

    codes = token_text_to_codes(token_text)
    if os.environ.get("ORPHEUS_VERBOSE", "0") == "1":
        print(f"Orpheus tokens: {len(codes)}", flush=True)
    return decode_snac_codes(codes)


# -----------------------------------------------------------------------------
# Downloads / smoke
# -----------------------------------------------------------------------------


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


def cmd_download_orpheus(args: argparse.Namespace) -> int:
    from huggingface_hub import hf_hub_download

    repo = "freddyaboulton/3b-de-ft-research_release-Q4_K_M-GGUF"
    filename = "3b-de-ft-research_release-q4_k_m.gguf"
    model_dir = VOICE_DIR / "models" / "orpheus"
    model_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=model_dir)
    print(path)
    return 0


def cmd_orpheus_path(args: argparse.Namespace) -> int:
    print(find_orpheus_model())
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    import importlib

    for mod in ["numpy", "sounddevice", "faster_whisper", "requests", "huggingface_hub"]:
        importlib.import_module(mod)
        print(f"OK import {mod}")
    print("piper executable:", shutil.which("piper"))
    return 0


def cmd_smoke_orpheus(args: argparse.Namespace) -> int:
    import importlib

    for mod in ["numpy", "torch", "snac"]:
        m = importlib.import_module(mod)
        print(f"OK import {mod}")
    import torch

    print("torch:", torch.__version__)
    print("torch.cuda.is_available:", torch.cuda.is_available())
    print("orpheus model:", find_orpheus_model() if _safe_find_orpheus() else "nicht gefunden")
    return 0


def _safe_find_orpheus() -> bool:
    try:
        find_orpheus_model()
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# STT + replies
# -----------------------------------------------------------------------------


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
    segments, _ = whisper.transcribe(
        audio,
        language="de",
        beam_size=int(os.environ.get("WHISPER_BEAM_SIZE", "5")),
        vad_filter=os.environ.get("WHISPER_VAD", "1") == "1",
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _extract_llm_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    c = choices[0]
    msg = c.get("message") or {}
    content = msg.get("content") or c.get("text") or c.get("content") or ""
    if isinstance(content, list):
        content = " ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content)
    text = str(content).strip()
    for marker in ["<|im_end|>", "<|endoftext|>", "<|eot_id|>", "</s>"]:
        text = text.replace(marker, "")
    return text.strip()


def reply_llama(text: str) -> str:
    url = os.environ.get("LLAMA_API_URL", "http://127.0.0.1:8080/v1/chat/completions")
    model = os.environ.get("LLAMA_MODEL", "qwen-local")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": os.environ.get(
                    "VOICE_SYSTEM_PROMPT",
                    "Antworte direkt auf Deutsch mit genau einem kurzen Satz. Kein Markdown. Kein Denken. Leicht trocken, gelegentlich mit Kaffee-Humor.",
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": float(os.environ.get("LLAMA_TEMP", "0.7")),
        "top_p": float(os.environ.get("LLAMA_TOP_P", "0.9")),
        "max_tokens": int(os.environ.get("LLAMA_MAX_TOKENS", "80")),
        "stream": False,
    }
    r = _HTTP.post(url, json=payload, timeout=int(os.environ.get("LLAMA_TIMEOUT", "120")))
    r.raise_for_status()
    data = r.json()
    if os.environ.get("VOICE_DEBUG_LLM", "0") == "1":
        Path("/tmp/voice_last_llm_response.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    answer = _extract_llm_text(data)
    return answer or "Ich habe gerade keine Antwort erhalten."


def make_reply(mode: str, text: str) -> str:
    if mode == "echo":
        return text
    if mode == "static":
        return "Ich habe dich verstanden."
    if mode == "llama":
        return reply_llama(text)
    raise ValueError(mode)


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------


def synthesize(text: str, tts: str) -> tuple[str, int, np.ndarray]:
    if tts == "piper":
        sr, audio = synthesize_piper(text)
        return "Piper", sr, audio
    if tts == "orpheus":
        sr, audio = synthesize_orpheus(text, mode="cli")
        return "Orpheus-CLI", sr, audio
    if tts == "orpheus-server":
        sr, audio = synthesize_orpheus(text, mode="server")
        return "Orpheus-Server", sr, audio
    raise ValueError(tts)


def cmd_tts(args: argparse.Namespace) -> int:
    text = " ".join(args.text).strip() or "Die Haustür ist noch offen."
    t0 = time.perf_counter()
    name, sr, audio = synthesize(text, args.tts)
    print(f"{name}: {len(audio)/sr:.2f}s Audio, sr={sr}, synth={time.perf_counter()-t0:.2f}s", flush=True)
    play_audio(sr, audio)
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    whisper = load_whisper()

    # Preload SNAC once for Orpheus modes so the first spoken answer is faster.
    if args.tts in {"orpheus", "orpheus-server"}:
        device = os.environ.get("SNAC_DEVICE", "cpu").strip() or "cpu"
        t0 = time.perf_counter()
        _get_snac_model(device)
        print(f"SNAC bereit ({device}) nach {time.perf_counter() - t0:.2f}s", flush=True)

    print(f"Voice Loop bereit. Reply={args.reply}, TTS={args.tts}. Abbruch mit Ctrl+C.", flush=True)

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
            _, sr, out = synthesize(answer, args.tts)
            play_audio(sr, out)
        except KeyboardInterrupt:
            print("\nBeendet.", flush=True)
            return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Minimal voice pipeline: Whisper -> reply -> Piper/Orpheus")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download-piper")
    d.add_argument("voice", nargs="?", help="Default: de_DE-thorsten-medium")
    d.set_defaults(func=cmd_download_piper)

    od = sub.add_parser("download-orpheus")
    od.set_defaults(func=cmd_download_orpheus)

    op = sub.add_parser("orpheus-path")
    op.set_defaults(func=cmd_orpheus_path)

    t = sub.add_parser("tts")
    t.add_argument("--tts", choices=["piper", "orpheus", "orpheus-server"], default=os.environ.get("VOICE_TTS", "piper"))
    t.add_argument("text", nargs="*")
    t.set_defaults(func=cmd_tts)

    l = sub.add_parser("loop")
    l.add_argument("--reply", choices=["echo", "static", "llama"], default="echo")
    l.add_argument("--tts", choices=["piper", "orpheus", "orpheus-server"], default=os.environ.get("VOICE_TTS", "piper"))
    l.set_defaults(func=cmd_loop)

    s = sub.add_parser("smoke")
    s.set_defaults(func=cmd_smoke)

    so = sub.add_parser("smoke-orpheus")
    so.set_defaults(func=cmd_smoke_orpheus)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
