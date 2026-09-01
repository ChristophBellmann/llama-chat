#!/usr/bin/env python3
"""TTS-Backends objektiv vergleichen: Latenz messen, WAV schreiben, zurueck-
transkribieren und mit dem Soll-Text abgleichen.

Ohne Rueck-Transkription faellt nicht auf, wenn ein Backend zwar Audio liefert,
aber den falschen Text spricht -- genau der Fall, der bei Orpheus mit dem
verkuerzten Prompt-Format auftrat.

Aufruf ueber ./voice/tts_check.sh (setzt venv und Umgebung).
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

DEFAULT_TEXT = "Lineare Regression beschreibt den Zusammenhang zwischen Merkmalen und Zielwert."


def save_wav(path: Path, sr: int, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes())


def normalize(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower(), flags=re.UNICODE)


def similarity(soll: str, ist: str) -> float:
    return difflib.SequenceMatcher(None, normalize(soll), normalize(ist)).ratio()


def transcribe(path: Path, model_size: str):
    from faster_whisper import WhisperModel

    key = f"_wm_{model_size}"
    model = globals().get(key)
    if model is None:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        globals()[key] = model
    segs, _ = model.transcribe(str(path), language="de")
    return " ".join(s.text.strip() for s in segs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", action="append", default=None,
                    help="Backend, mehrfach angebbar (piper, neutts, orpheus-server, orpheus)")
    ap.add_argument("--runs", type=int, default=3, help="Laeufe pro Backend")
    ap.add_argument("--whisper", default="small", help="faster-whisper Modell (tiny/base/small/medium)")
    ap.add_argument("--outdir", default=None, help="Zielordner fuer die WAVs")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("text", nargs="*")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import voice_app as va

    text = " ".join(args.text).strip() or DEFAULT_TEXT
    backends = args.tts or ["piper", "neutts", "orpheus-server"]
    outdir = Path(args.outdir or (Path(__file__).resolve().parent / "tts_check_out"))

    print(f"SOLL: {text}\n")
    rows = []
    for be in backends:
        for run in range(1, args.runs + 1):
            tag = be if args.runs == 1 else f"{be}_{run}"
            wav = outdir / f"{tag}.wav"
            try:
                t0 = time.perf_counter()
                name, sr, audio = va.synthesize(text, be)
                synth = time.perf_counter() - t0
            except Exception as e:
                print(f"{tag:22s} FEHLER: {type(e).__name__}: {e}")
                rows.append((tag, None, None, None, f"FEHLER: {e}"))
                continue
            save_wav(wav, sr, audio)
            dur = len(audio) / sr
            txt = "" if args.no_transcribe else transcribe(wav, args.whisper)
            sim = similarity(text, txt) if txt else float("nan")
            rows.append((tag, synth, dur, sim, txt))
            print(f"{tag:22s} synth={synth:6.2f}s  audio={dur:5.2f}s  "
                  f"rtf={synth/dur if dur else float('nan'):5.2f}  aehnlichkeit={sim:.2f}")
            if txt:
                print(f"{'':22s} -> {txt}")
            print(f"{'':22s}    {wav}")

    print("\n" + "=" * 78)
    print(f"{'Backend':16s} {'cold':>9s} {'warm (Mittel)':>15s} {'audio':>8s} "
          f"{'RTF warm':>9s} {'Text-Treue':>11s}")
    print("-" * 78)
    for be in backends:
        mine = [r for r in rows if r[0] == be or r[0].startswith(be + "_")]
        ok = [r for r in mine if r[1] is not None]
        if not ok:
            print(f"{be:16s} {'FEHLER':>9s}")
            continue
        cold = ok[0][1]
        warm = [r[1] for r in ok[1:]]
        warm_m = sum(warm) / len(warm) if warm else float("nan")
        dur = sum(r[2] for r in ok) / len(ok)
        sims = [r[3] for r in ok if r[3] == r[3]]
        sim_m = sum(sims) / len(sims) if sims else float("nan")
        warm_s = f"{warm_m:.2f}s" if warm else "n/a"
        rtf_s = f"{warm_m/dur:.2f}" if warm and dur else "n/a"
        print(f"{be:16s} {cold:8.2f}s {warm_s:>15s} {dur:7.2f}s {rtf_s:>9s} {sim_m:10.2f}")
    print("\ncold = 1. Lauf (Modell/Referenz noch nicht geladen), warm = Mittel ab Lauf 2.")
    print("RTF < 1 heisst schneller als Echtzeit -- nur dann taugt es fuer den Live-Loop.")
    print("Text-Treue 1.00 = Transkript deckt sich mit dem Soll-Text (Whisper-Fehler")
    print("druecken den Wert leicht; unter ~0.8 spricht das Backend etwas anderes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
