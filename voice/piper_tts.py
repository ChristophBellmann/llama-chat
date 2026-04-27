#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np


class PiperTTS:
    def __init__(self, model_path: str | None = None, config_path: str | None = None, piper_bin: str | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        voice_dir = root / "voice"

        self.model_path = Path(
            model_path
            or os.environ.get("PIPER_MODEL", "")
            or self._find_default_model(voice_dir)
        )

        if not self.model_path.exists():
            raise FileNotFoundError(
                "Piper-Modell nicht gefunden. Erst ausführen:\n"
                "  ./voice/download_piper_de.sh\n"
                "oder PIPER_MODEL=/pfad/model.onnx setzen."
            )

        self.config_path = Path(
            config_path
            or os.environ.get("PIPER_CONFIG", "")
            or f"{self.model_path}.json"
        )

        self.piper_bin = piper_bin or os.environ.get("PIPER_BIN", "") or self._find_piper_bin(voice_dir)
        if not self.piper_bin:
            raise FileNotFoundError("piper executable nicht gefunden. Erst ./voice/setup_piper_env.sh ausführen.")

    @staticmethod
    def _find_default_model(voice_dir: Path) -> str:
        models = sorted((voice_dir / "models" / "piper").rglob("de_DE-thorsten-medium.onnx"))
        if models:
            return str(models[-1])
        models = sorted((voice_dir / "models" / "piper").rglob("*.onnx"))
        return str(models[-1]) if models else str(voice_dir / "models" / "piper" / "de_DE-thorsten-medium.onnx")

    @staticmethod
    def _find_piper_bin(voice_dir: Path) -> str | None:
        cand = voice_dir / ".venv" / "bin" / "piper"
        if cand.exists():
            return str(cand)
        return shutil.which("piper")

    @staticmethod
    def _read_wav(path: Path) -> tuple[int, np.ndarray]:
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

    def synthesize(self, text: str) -> tuple[int, np.ndarray]:
        text = text.strip()
        if not text:
            return 24000, np.zeros(0, dtype=np.float32)

        with tempfile.NamedTemporaryFile(prefix="piper_", suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        cmd = [
            self.piper_bin,
            "--model", str(self.model_path),
            "--output_file", str(wav_path),
        ]

        if self.config_path.exists():
            cmd.extend(["--config", str(self.config_path)])

        proc = subprocess.run(
            cmd,
            input=text + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if proc.returncode != 0:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"piper failed exit={proc.returncode}\n{proc.stderr}")

        try:
            return self._read_wav(wav_path)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
