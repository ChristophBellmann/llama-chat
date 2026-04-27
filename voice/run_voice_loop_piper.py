#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from typing import Generator, Iterable

import numpy as np
import requests
from faster_whisper import WhisperModel

from audio_streams import MicTurnDetector, StreamingAudioOutput, VadConfig
from piper_tts import PiperTTS


SENTENCE_RE = re.compile(r"(.+?[.!?。！？]\s+|.+?\n+)", re.S)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sentence_chunks(token_stream: Iterable[str], min_chars: int = 70, max_chars: int = 190) -> Generator[str, None, None]:
    buf = ""
    for tok in token_stream:
        if not tok:
            continue
        buf += tok
        while True:
            m = SENTENCE_RE.match(buf)
            if not m:
                break
            chunk = clean_text(m.group(1))
            buf = buf[m.end():]
            if chunk:
                yield chunk
        if len(buf) >= max_chars:
            cut = buf.rfind(" ", 0, max_chars)
            if cut < min_chars:
                cut = max_chars
            chunk = clean_text(buf[:cut])
            buf = buf[cut:]
            if chunk:
                yield chunk
    tail = clean_text(buf)
    if tail:
        yield tail


def llama_stream_reply(prompt: str, url: str, model: str, api_key: str, timeout: float, system_prompt: str) -> Generator[str, None, None]:
    payload = {
        "model": model,
        "stream": True,
        "temperature": 0.4,
        "max_tokens": 180,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                token = obj["choices"][0].get("delta", {}).get("content") or ""
            except Exception:
                token = ""
            if token:
                yield token


def make_reply_chunks(args, user_text: str) -> Generator[str, None, None]:
    if args.reply == "echo":
        yield user_text
        return

    if args.reply == "static":
        yield args.static_text
        return

    if args.reply == "llama":
        token_stream = llama_stream_reply(
            prompt=user_text,
            url=args.llama_url,
            model=args.llama_model,
            api_key=args.llama_api_key,
            timeout=args.llama_timeout,
            system_prompt=args.system_prompt,
        )
        yield from sentence_chunks(token_stream, min_chars=args.min_tts_chars, max_chars=args.max_tts_chars)
        return

    raise ValueError(args.reply)


def transcribe_audio(whisper: WhisperModel, audio: np.ndarray, language: str) -> str:
    segments, _info = whisper.transcribe(
        audio,
        language=language,
        beam_size=1,
        best_of=1,
        vad_filter=False,
        condition_on_previous_text=False,
        temperature=0.0,
        word_timestamps=False,
    )
    return clean_text(" ".join(seg.text.strip() for seg in segments))


def speak_chunks(tts: PiperTTS, out_holder: dict, chunks: Iterable[str], playback_active: threading.Event, post_mute: float) -> None:
    playback_active.set()
    try:
        for chunk in chunks:
            if not chunk:
                continue
            print(f"TTS:  {chunk}", flush=True)
            sr, audio = tts.synthesize(chunk)

            out = out_holder.get("out")
            if out is None or out.samplerate != sr:
                if out is not None:
                    out.close()
                out = StreamingAudioOutput(samplerate=sr)
                out_holder["out"] = out

            out.write(sr, audio)
            out.drain()
    finally:
        time.sleep(post_mute)
        playback_active.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokaler Voice-Loop: Mic -> Whisper -> Reply -> Piper -> Speaker.")
    parser.add_argument("--reply", choices=["echo", "static", "llama"], default=os.environ.get("REPLY", "echo"))
    parser.add_argument("--static-text", default="Verstanden.")
    parser.add_argument("--language", default=os.environ.get("WHISPER_LANG", "de"))
    parser.add_argument("--whisper-model", default=os.environ.get("WHISPER_MODEL", "tiny"))
    parser.add_argument("--start-rms", type=float, default=float(os.environ.get("START_RMS", "0.018")))
    parser.add_argument("--stop-rms", type=float, default=float(os.environ.get("STOP_RMS", "0.010")))
    parser.add_argument("--end-silence", type=float, default=float(os.environ.get("END_SILENCE", "0.55")))
    parser.add_argument("--mic-block-ms", type=int, default=int(os.environ.get("MIC_BLOCK_MS", "20")))
    parser.add_argument("--post-playback-mute", type=float, default=0.12)
    parser.add_argument("--llama-url", default=os.environ.get("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions"))
    parser.add_argument("--llama-model", default=os.environ.get("LLAMA_MODEL", "qwen-local"))
    parser.add_argument("--llama-api-key", default=os.environ.get("API_KEY", "sk-local"))
    parser.add_argument("--llama-timeout", type=float, default=120.0)
    parser.add_argument("--min-tts-chars", type=int, default=70)
    parser.add_argument("--max-tts-chars", type=int, default=190)
    parser.add_argument("--system-prompt", default="Antworte sehr kurz, sachlich und auf Deutsch. Maximal zwei Sätze.")
    args = parser.parse_args()

    print(f"Lade faster-whisper: {args.whisper_model} / int8 CPU", flush=True)
    whisper = WhisperModel(
        args.whisper_model,
        device="cpu",
        compute_type="int8",
        cpu_threads=os.cpu_count() or 4,
        num_workers=1,
    )

    print("Lade Piper...", flush=True)
    tts = PiperTTS()

    playback_active = threading.Event()
    out_holder: dict = {"out": None}
    mic = MicTurnDetector(
        VadConfig(
            block_ms=args.mic_block_ms,
            start_rms=args.start_rms,
            stop_rms=args.stop_rms,
            end_silence_s=args.end_silence,
        ),
        playback_active=playback_active,
    )

    print("Bereit. Sprechen, dann kurze Pause. Strg+C beendet.", flush=True)
    print(f"Mode={args.reply}", flush=True)

    try:
        mic.start()
        while True:
            t0 = time.perf_counter()
            audio = mic.listen_once()
            t1 = time.perf_counter()

            text = transcribe_audio(whisper, audio, args.language)
            t2 = time.perf_counter()

            if not text:
                continue

            print(f"Du:   {text}", flush=True)
            print(f"Timing: listen={t1 - t0:.2f}s stt={t2 - t1:.2f}s audio={len(audio)/16000:.2f}s", flush=True)

            chunks = make_reply_chunks(args, text)
            speak_chunks(tts, out_holder, chunks, playback_active, args.post_playback_mute)
            mic.flush()

    except KeyboardInterrupt:
        print("\nBeendet.", flush=True)
    finally:
        mic.close()
        out = out_holder.get("out")
        if out is not None:
            out.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
