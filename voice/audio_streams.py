#!/usr/bin/env python3
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd


@dataclass
class VadConfig:
    sample_rate: int = 16000
    block_ms: int = 20
    start_rms: float = 0.018
    stop_rms: float = 0.010
    end_silence_s: float = 0.55
    max_speech_s: float = 12.0
    preroll_s: float = 0.25


class StreamingAudioOutput:
    def __init__(self, samplerate: int = 24000, channels: int = 1, blocksize: int = 1024) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=128)
        self.closed = False

        self.stream = sd.OutputStream(
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            blocksize=blocksize,
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            pass

        out = np.zeros((frames, self.channels), dtype=np.float32)
        filled = 0

        while filled < frames:
            try:
                chunk = self.q.get_nowait()
            except queue.Empty:
                break

            if chunk is None:
                break

            chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
            n = min(frames - filled, len(chunk))
            out[filled:filled+n, 0] = chunk[:n]
            filled += n

            rest = chunk[n:]
            if len(rest):
                try:
                    self.q.put_nowait(rest)
                except queue.Full:
                    pass
                break

        outdata[:] = out

    def write(self, samplerate: int, audio: np.ndarray) -> None:
        if self.closed:
            return
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samplerate != self.samplerate:
            # Simple fallback resampler for 16/22.05/24 kHz style cases.
            x_old = np.linspace(0.0, 1.0, len(audio), endpoint=False)
            new_len = max(1, int(len(audio) * self.samplerate / samplerate))
            x_new = np.linspace(0.0, 1.0, new_len, endpoint=False)
            audio = np.interp(x_new, x_old, audio).astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        self.q.put(audio)

    def drain(self) -> None:
        while not self.q.empty():
            time.sleep(0.02)

    def close(self) -> None:
        self.closed = True
        try:
            self.q.put_nowait(None)
        except Exception:
            pass
        self.stream.stop()
        self.stream.close()


class MicTurnDetector:
    def __init__(self, cfg: VadConfig, playback_active: threading.Event | None = None) -> None:
        self.cfg = cfg
        self.playback_active = playback_active or threading.Event()
        self.block_samples = int(cfg.sample_rate * cfg.block_ms / 1000)
        self.q: queue.Queue[np.ndarray] = queue.Queue()
        self.closed = False
        self.stream = sd.InputStream(
            samplerate=cfg.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block_samples,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status) -> None:
        if self.closed or self.playback_active.is_set():
            return
        audio = np.asarray(indata[:, 0], dtype=np.float32).copy()
        self.q.put(audio)

    def start(self) -> None:
        self.stream.start()

    def flush(self) -> None:
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                return

    def listen_once(self) -> np.ndarray:
        cfg = self.cfg
        preroll_blocks = max(1, int(cfg.preroll_s / (cfg.block_ms / 1000)))
        preroll: list[np.ndarray] = []
        recording: list[np.ndarray] = []
        in_speech = False
        silence_s = 0.0
        speech_s = 0.0

        while True:
            block = self.q.get()
            rms = float(np.sqrt(np.mean(block * block) + 1e-12))

            if not in_speech:
                preroll.append(block)
                preroll = preroll[-preroll_blocks:]
                if rms >= cfg.start_rms:
                    in_speech = True
                    recording.extend(preroll)
                    preroll.clear()
                continue

            recording.append(block)
            speech_s += cfg.block_ms / 1000

            if rms < cfg.stop_rms:
                silence_s += cfg.block_ms / 1000
            else:
                silence_s = 0.0

            if silence_s >= cfg.end_silence_s or speech_s >= cfg.max_speech_s:
                audio = np.concatenate(recording).astype(np.float32)
                return audio

    def close(self) -> None:
        self.closed = True
        self.stream.stop()
        self.stream.close()
