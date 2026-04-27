#!/usr/bin/env python3
from __future__ import annotations

import sys
import time

from audio_streams import StreamingAudioOutput
from piper_tts import PiperTTS


def main() -> int:
    text = " ".join(sys.argv[1:]).strip() or "Die Haustür ist noch offen."

    print("Lade Piper...", flush=True)
    t0 = time.perf_counter()
    tts = PiperTTS()
    print(f"Piper bereit nach {time.perf_counter() - t0:.2f}s", flush=True)

    sr, audio = tts.synthesize(text)
    print(f"Audio: {len(audio) / sr:.2f}s, sr={sr}", flush=True)

    out = StreamingAudioOutput(samplerate=sr)
    try:
        out.write(sr, audio)
        out.drain()
        time.sleep(0.2)
    finally:
        out.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
