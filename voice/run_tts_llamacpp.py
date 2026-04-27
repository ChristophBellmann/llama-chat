#!/usr/bin/env python3
from __future__ import annotations

import sys
import time

from audio_streams import StreamingAudioOutput
from llamacpp_orpheus import from_env


def main() -> int:
    text = " ".join(sys.argv[1:]).strip() or "Die Haustür ist noch offen."

    print("Lade llama.cpp-Orpheus Backend...", flush=True)
    t0 = time.perf_counter()
    tts = from_env()
    print(f"Backend bereit nach {time.perf_counter() - t0:.2f}s", flush=True)

    out = StreamingAudioOutput(samplerate=24000)
    first = None
    chunks = 0
    samples = 0

    try:
        for sr, audio in tts.stream_tts(text):
            if first is None:
                first = time.perf_counter()
                print(f"First audio nach {first - t0:.2f}s", flush=True)
            chunks += 1
            samples += len(audio)
            out.write(sr, audio)
        out.drain()
        time.sleep(0.2)
    finally:
        out.close()

    if samples:
        audio_s = samples / 24000
        wall_s = time.perf_counter() - t0
        print(f"chunks={chunks}")
        print(f"audio={audio_s:.2f}s")
        print(f"wall={wall_s:.2f}s")
        print(f"RTF={wall_s / max(audio_s, 1e-9):.2f}")
    else:
        print("Keine Audio-Tokens empfangen.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
