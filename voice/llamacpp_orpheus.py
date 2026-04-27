#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

import numpy as np


CUSTOM_RE = re.compile(r"<custom_token_(\d+)>")


def find_default_orpheus_model(lang: str = "de") -> Optional[str]:
    explicit = os.environ.get("ORPHEUS_MODEL_PATH", "").strip()
    if explicit:
        return explicit

    if lang != "de":
        return None

    base = Path.home() / ".cache/huggingface/hub"
    pattern = (
        "models--freddyaboulton--3b-de-ft-research_release-Q4_K_M-GGUF"
        "/snapshots/*/3b-de-ft-research_release-q4_k_m.gguf"
    )
    matches = sorted(base.glob(pattern))
    if matches:
        return str(matches[-1])
    return None


@dataclass
class LlamaCppOrpheusConfig:
    root_dir: str
    model_path: Optional[str]
    lang: str = "de"
    voice: str = "jana"
    gpu_layers: str = "0"
    ctx_size: int = 2048
    threads: int = 6
    n_predict: int = 300
    batch: int = 8
    ubatch: int = 4
    temp: float = 0.6
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    verbose: bool = False


class SnacDecoder:
    def __init__(self) -> None:
        import torch
        from snac import SNAC

        self.torch = torch
        self.device = os.environ.get("SNAC_DEVICE", "").strip() or "cpu"
        self.model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to(self.device)

    def decode_codes(self, frame_codes: list[int]) -> Optional[np.ndarray]:
        torch = self.torch
        if len(frame_codes) < 28:
            return None

        frame_codes = frame_codes[-28:]
        c0, c1, c2 = [], [], []
        for j in range(4):
            i = 7 * j
            c0.append(frame_codes[i])
            c1.extend([frame_codes[i + 1], frame_codes[i + 4]])
            c2.extend([frame_codes[i + 2], frame_codes[i + 3], frame_codes[i + 5], frame_codes[i + 6]])

        codes = [
            torch.tensor(c0, device=self.device, dtype=torch.int32).unsqueeze(0),
            torch.tensor(c1, device=self.device, dtype=torch.int32).unsqueeze(0),
            torch.tensor(c2, device=self.device, dtype=torch.int32).unsqueeze(0),
        ]

        for c in codes:
            if torch.any(c < 0) or torch.any(c > 4095):
                return None

        with torch.inference_mode():
            audio_hat = self.model.decode(codes)

        audio = audio_hat[:, :, 2048:4096].detach().cpu().numpy().reshape(-1).astype(np.float32)
        return np.clip(audio, -1.0, 1.0)


class LlamaCppOrpheus:
    def __init__(self, cfg: LlamaCppOrpheusConfig) -> None:
        self.cfg = cfg
        self.root = Path(cfg.root_dir)
        self.llama_completion = self.root / "llama.cpp" / "build" / "bin" / "llama-completion"
        if not self.llama_completion.exists():
            raise FileNotFoundError(f"llama-completion nicht gefunden: {self.llama_completion}")

        self.model_path = cfg.model_path or find_default_orpheus_model(cfg.lang)
        if not self.model_path:
            raise FileNotFoundError("Kein Orpheus-DE-GGUF gefunden. Setze ORPHEUS_MODEL_PATH=/pfad/zum/model.gguf")

        self.decoder = SnacDecoder()

    def format_prompt(self, text: str) -> str:
        return (
            f"<custom_token_3><|begin_of_text|>"
            f"{self.cfg.voice}: {text}"
            f"<|eot_id|><custom_token_4><custom_token_5><custom_token_1>"
        )

    @staticmethod
    def token_to_code(token_text: str, index: int) -> Optional[int]:
        m = CUSTOM_RE.search(token_text)
        if not m:
            return None
        raw = int(m.group(1))
        code = raw - 10 - ((index % 7) * 4096)
        if code < 0 or code > 4095:
            return None
        return code

    def iter_custom_tokens(self, text: str) -> Generator[str, None, None]:
        prompt = self.format_prompt(text)
        cmd = [
            str(self.llama_completion),
            "--model", str(self.model_path),
            "--prompt", prompt,
            "--ctx-size", str(self.cfg.ctx_size),
            "--threads", str(self.cfg.threads),
            "--gpu-layers", str(self.cfg.gpu_layers),
            "--n-predict", str(self.cfg.n_predict),
            "--temp", str(self.cfg.temp),
            "--top-p", str(self.cfg.top_p),
            "--repeat-penalty", str(self.cfg.repeat_penalty),
            "--batch-size", str(self.cfg.batch),
            "--ubatch-size", str(self.cfg.ubatch),
            "--no-display-prompt",
            "--simple-io",
            "--color", "off",
            "--special",
            "--ignore-eos",
            "-no-cnv",
            "--no-warmup",
            "--flash-attn", "off",
        ]
        if not self.cfg.verbose:
            cmd.insert(1, "--log-disable")

        env = dict(os.environ)
        bin_dir = str(self.root / "llama.cpp" / "build" / "bin")
        env["LD_LIBRARY_PATH"] = f"{bin_dir}:{env.get('LD_LIBRARY_PATH', '')}"

        if self.cfg.verbose:
            print("llama-completion:", " ".join(shlex.quote(x) for x in cmd), flush=True)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=None if self.cfg.verbose else subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        assert proc.stdout is not None

        buf = ""
        while True:
            ch = proc.stdout.read(1)
            if ch == "" and proc.poll() is not None:
                break
            if not ch:
                continue
            buf += ch
            while True:
                m = CUSTOM_RE.search(buf)
                if not m:
                    keep = buf.rfind("<custom_token_")
                    buf = buf[keep:] if keep >= 0 else buf[-64:]
                    break
                yield m.group(0)
                buf = buf[m.end():]

        rc = proc.wait()
        if rc != 0:
            err = proc.stderr.read() if proc.stderr is not None else ""
            raise RuntimeError(f"llama-completion failed with exit={rc}\n{err}")

    def stream_tts(self, text: str) -> Generator[tuple[int, np.ndarray], None, None]:
        codes: list[int] = []
        idx = 0
        for token_text in self.iter_custom_tokens(text):
            code = self.token_to_code(token_text, idx)
            idx += 1
            if code is None:
                continue
            codes.append(code)
            if len(codes) >= 28 and len(codes) % 7 == 0:
                audio = self.decoder.decode_codes(codes[-28:])
                if audio is not None and audio.size:
                    yield 24_000, audio


def from_env() -> LlamaCppOrpheus:
    cfg = LlamaCppOrpheusConfig(
        root_dir=os.environ.get("LLAMA_CHAT_ROOT", "/media/christoph/some_space/Compute/ML-Lab/llama-chat"),
        model_path=os.environ.get("ORPHEUS_MODEL_PATH", "").strip() or None,
        lang=os.environ.get("ORPHEUS_LANG", "de"),
        voice=os.environ.get("ORPHEUS_VOICE", "jana"),
        gpu_layers=os.environ.get("ORPHEUS_GPU_LAYERS", "0"),
        ctx_size=int(os.environ.get("ORPHEUS_CTX", "2048")),
        threads=int(os.environ.get("ORPHEUS_THREADS", "6")),
        n_predict=int(os.environ.get("ORPHEUS_N_PREDICT", "300")),
        batch=int(os.environ.get("ORPHEUS_BATCH", "8")),
        ubatch=int(os.environ.get("ORPHEUS_UBATCH", "4")),
        temp=float(os.environ.get("ORPHEUS_TEMP", "0.6")),
        top_p=float(os.environ.get("ORPHEUS_TOP_P", "0.9")),
        repeat_penalty=float(os.environ.get("ORPHEUS_REPEAT_PENALTY", "1.1")),
        verbose=os.environ.get("ORPHEUS_VERBOSE", "0") == "1",
    )
    return LlamaCppOrpheus(cfg)
