#!/usr/bin/env python3
import argparse
import asyncio
import logging
import math
import os
import signal
from functools import partial
from pathlib import Path

import numpy as np
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer
from wyoming.tts import Synthesize

_LOGGER = logging.getLogger(__name__)

_NEUTTS: dict = {}


def _get_neutts(backbone: str, codec: str, device: str):
    if "tts" not in _NEUTTS:
        from neutts import NeuTTS

        _NEUTTS["tts"] = NeuTTS(
            backbone_repo=backbone,
            backbone_device=device,
            codec_repo=codec,
            codec_device=device,
        )
    return _NEUTTS["tts"]


def _get_voice_wavs(ref_path: str) -> dict[str, Path]:
    p = Path(ref_path)
    if p.is_file():
        return {p.stem: p}
    wavs = {}
    for f in sorted(p.glob("*.wav")):
        wavs[f.stem] = f
    return wavs


def _get_voice_codes(tts, name: str, wav: Path):
    key = f"ref:{name}"
    if key not in _NEUTTS:
        _NEUTTS[key] = tts.encode_reference(str(wav))
    txt = wav.with_suffix(".txt")
    ref_text = txt.read_text().strip() if txt.exists() else ""
    return _NEUTTS[key], ref_text


class NeuTTSHandler(AsyncEventHandler):
    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        voice_wavs: dict[str, Path],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info_event = wyoming_info.event()
        self.cli_args = cli_args
        self.voice_wavs = voice_wavs

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            return True

        if not Synthesize.is_type(event.type):
            return True

        synthesize = Synthesize.from_event(event)
        text = " ".join(synthesize.text.strip().splitlines())
        if not text:
            return True

        try:
            voice_name = self.cli_args.voice
            if synthesize.voice is not None and synthesize.voice.name:
                voice_name = synthesize.voice.name

            wav = self.voice_wavs.get(voice_name)
            if wav is None:
                wav = next(iter(self.voice_wavs.values()))

            tts = _get_neutts(
                self.cli_args.backbone, self.cli_args.codec, self.cli_args.device
            )
            ref_codes, ref_text_str = _get_voice_codes(tts, voice_name, wav)
            ref_text_str = ref_text_str or text

            wav_audio = tts.infer(text, ref_codes, ref_text_str)

            audio_int16 = (np.clip(wav_audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            rate = 24000
            width = 2
            channels = 1

            await self.write_event(
                AudioStart(rate=rate, width=width, channels=channels).event()
            )

            bytes_per_chunk = width * channels * self.cli_args.samples_per_chunk
            num_chunks = max(1, int(math.ceil(len(audio_int16) / bytes_per_chunk)))
            for i in range(num_chunks):
                offset = i * bytes_per_chunk
                chunk = audio_int16[offset : offset + bytes_per_chunk]
                await self.write_event(
                    AudioChunk(
                        audio=chunk, rate=rate, width=width, channels=channels
                    ).event()
                )

            await self.write_event(AudioStop().event())
        except Exception as err:
            await self.write_event(
                Error(text=str(err), code=err.__class__.__name__).event()
            )
            raise

        return True


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:10400")
    parser.add_argument("--voice", default="greta", help="Default-Stimme")
    parser.add_argument(
        "--ref-audio",
        required=True,
        help="Pfad zur .wav oder Ordner mit .wav-Dateien (jede = eigene Stimme)",
    )
    parser.add_argument("--backbone", default="neuphonic/neutts-nano-german-q4-gguf")
    parser.add_argument("--codec", default="neuphonic/neucodec")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--samples-per-chunk", type=int, default=1024)
    parser.add_argument("--zeroconf", nargs="?", const="neutts", help="Zeroconf name")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--log-format", default=logging.BASIC_FORMAT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format=args.log_format
    )

    args.ref_audio = os.path.abspath(args.ref_audio)
    voice_wavs = _get_voice_wavs(args.ref_audio)

    if not voice_wavs:
        _LOGGER.error("Keine .wav Dateien gefunden in %s", args.ref_audio)
        return

    _LOGGER.info(
        "%d Stimmen geladen: %s", len(voice_wavs), ", ".join(voice_wavs.keys())
    )

    voices = [
        TtsVoice(
            name=name,
            description=f"NeuTTS ({name})",
            installed=True,
            languages=["de"],
            attribution=Attribution(
                name="neuphonic", url="https://github.com/neuphonic/neutts"
            ),
            version="0.1",
        )
        for name in sorted(voice_wavs)
    ]

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="neutts",
                description="NeuTTS Nano German neural TTS mit Voice Cloning",
                attribution=Attribution(
                    name="neuphonic", url="https://github.com/neuphonic/neutts"
                ),
                installed=True,
                voices=voices,
                version="0.1",
            )
        ],
    )

    server = AsyncServer.from_uri(args.uri)

    if args.zeroconf:
        if not isinstance(server, AsyncTcpServer):
            raise ValueError("Zeroconf requires tcp:// uri")
        from wyoming.zeroconf import HomeAssistantZeroconf

        tcp_server: AsyncTcpServer = server
        hass_zeroconf = HomeAssistantZeroconf(
            name=args.zeroconf, port=tcp_server.port, host=tcp_server.host
        )
        await hass_zeroconf.register_server()
        _LOGGER.info("Zeroconf als '%s' aktiviert", args.zeroconf)

    _LOGGER.info("NeuTTS Wyoming server bereit auf %s", args.uri)
    server_task = asyncio.create_task(
        server.run(partial(NeuTTSHandler, wyoming_info, args, voice_wavs))
    )

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, server_task.cancel)
    loop.add_signal_handler(signal.SIGTERM, server_task.cancel)

    try:
        await server_task
    except asyncio.CancelledError:
        _LOGGER.info("Server gestoppt")


def run():
    asyncio.run(main())


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
