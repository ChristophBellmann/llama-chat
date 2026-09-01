#!/usr/bin/env python3
"""Wyoming-TTS-Server für Orpheus-DE auf der Workstation.

Anders als die NeuTTS-Vorlage daneben wird hier nicht erst komplett
synthetisiert und danach zerlegt: Das Wyoming-Protokoll ist mit
AudioStart -> AudioChunk* -> AudioStop von Haus aus streamfähig, und Orpheus
generiert nur knapp schneller als Echtzeit. Die Chunks gehen deshalb raus,
während das Modell noch generiert -- sonst wartet Home Assistant rund sieben
Sekunden auf den ersten Ton statt unter einer Sekunde.

Setzt einen laufenden Orpheus-llama-server voraus (./start_orpheus_de_server.sh,
Port 8082) und nutzt dessen Streaming-Pfad aus voice/voice_app.py.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from functools import partial
from pathlib import Path

import numpy as np
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer

_LOGGER = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "voice"))

RATE = 24000
WIDTH = 2
CHANNELS = 1

# Stimmen des DE-Finetunes. julia ist bewusst nicht dabei: das Modell kennt sie
# nicht und liest den Namen dann vor.
VOICES = ["jana", "thomas"]


class OrpheusHandler(AsyncEventHandler):
    def __init__(self, wyoming_info: Info, cli_args, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info_event = wyoming_info.event()
        self.cli_args = cli_args

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            return True

        from wyoming.tts import Synthesize

        if not Synthesize.is_type(event.type):
            return True

        synthesize = Synthesize.from_event(event)
        text = " ".join(synthesize.text.strip().splitlines())
        if not text:
            return True

        voice = self.cli_args.voice
        if synthesize.voice is not None and synthesize.voice.name:
            voice = synthesize.voice.name

        _LOGGER.info("Synthese (%s): %s", voice, text[:80])
        t0 = time.perf_counter()

        try:
            await self.write_event(
                AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event()
            )

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            stop_event = threading.Event()

            def produce() -> None:
                """Läuft im Thread: der Generator ist blockierendes HTTP + Torch."""
                try:
                    import voice_app as va

                    os.environ["ORPHEUS_VOICE"] = voice
                    gen = va.stream_orpheus_audio(text)
                    try:
                        for _sr, chunk in gen:
                            if stop_event.is_set():
                                break
                            loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    finally:
                        # Schliesst den HTTP-Stream und gibt den GPU-Slot frei.
                        # Ohne das rechnet das Modell nach dem Kuerzen weiter:
                        # im Test 11 der 19 Sekunden fuer Audio, das niemand
                        # mehr hoert.
                        gen.close()
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception as err:  # an den Event-Loop weiterreichen
                    loop.call_soon_threadsafe(queue.put_nowait, err)

            await loop.run_in_executor(None, lambda: None)  # Executor vorwärmen
            task = loop.run_in_executor(None, produce)

            # Standardmaessig ohne Obergrenze: lange Texte werden vollstaendig
            # gesprochen. Seit der Textsegmentierung gilt n_predict je Segment,
            # ein langer Text kann also beliebig viel Audio erzeugen -- eine
            # erbetene Geschichte ergab 126 s Audio in 117 s Synthese. Wer das
            # begrenzen will, setzt ORPHEUS_MAX_AUDIO_S; dann wird gekuerzt und
            # die Generierung abgebrochen.
            max_samples = int(self.cli_args.max_audio_seconds * RATE)
            gekuerzt = False

            first = None
            total = 0
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                if max_samples and total // (WIDTH * CHANNELS) >= max_samples:
                    if not gekuerzt:
                        _LOGGER.warning(
                            "Obergrenze von %.0fs erreicht, Generierung "
                            "abgebrochen (Text war %d Zeichen)",
                            self.cli_args.max_audio_seconds,
                            len(text),
                        )
                        gekuerzt = True
                        stop_event.set()
                    continue
                if first is None:
                    first = time.perf_counter() - t0
                pcm = (np.clip(item, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                total += len(pcm)
                step = WIDTH * CHANNELS * self.cli_args.samples_per_chunk
                for off in range(0, len(pcm), step):
                    await self.write_event(
                        AudioChunk(
                            audio=pcm[off : off + step],
                            rate=RATE,
                            width=WIDTH,
                            channels=CHANNELS,
                        ).event()
                    )
            await task

            # Der Satellit schneidet sonst das letzte Wort ab. Das Audio selbst
            # ist vollstaendig -- gemessen endet es sauber in Stille --, aber der
            # Player beendet die Wiedergabe ein Stueck vor dem Stream-Ende. Die
            # natuerliche Ausklingzeit von rund 150 ms reicht als Puffer nicht.
            tail_ms = max(0, int(self.cli_args.tail_silence_ms))
            if tail_ms:
                n_samples = int(RATE * tail_ms / 1000)
                silence = b"\x00" * (n_samples * WIDTH * CHANNELS)
                step = WIDTH * CHANNELS * self.cli_args.samples_per_chunk
                for off in range(0, len(silence), step):
                    await self.write_event(
                        AudioChunk(
                            audio=silence[off : off + step],
                            rate=RATE,
                            width=WIDTH,
                            channels=CHANNELS,
                        ).event()
                    )

            await self.write_event(AudioStop().event())
            dur = total / (RATE * WIDTH * CHANNELS)
            _LOGGER.info(
                "fertig: %.2fs Audio%s, erster Chunk nach %.2fs, gesamt %.2fs",
                dur,
                " (gekuerzt)" if gekuerzt else "",
                first if first is not None else -1.0,
                time.perf_counter() - t0,
            )
        except Exception as err:
            _LOGGER.exception("Synthese fehlgeschlagen")
            await self.write_event(
                Error(text=str(err), code=err.__class__.__name__).event()
            )
            return True

        return True


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:10401")
    parser.add_argument("--voice", default="jana")
    parser.add_argument("--samples-per-chunk", type=int, default=1024)
    parser.add_argument(
        "--completion-url", default="http://127.0.0.1:8082/completion"
    )
    parser.add_argument("--snac-device", default="cpu")
    parser.add_argument(
        "--tail-silence-ms",
        type=int,
        default=int(os.environ.get("ORPHEUS_TAIL_SILENCE_MS", "400")),
        help="Stille am Ende jeder Antwort, damit der Satellit das letzte Wort "
        "nicht abschneidet; 0 schaltet sie ab",
    )
    parser.add_argument(
        "--max-audio-seconds",
        type=float,
        default=float(os.environ.get("ORPHEUS_MAX_AUDIO_S", "0")),
        help="Obergrenze je Anfrage in Sekunden. Standard 0 = keine Grenze, "
        "lange Texte werden vollstaendig gesprochen. Ein Wert > 0 kuerzt und "
        "bricht die Generierung ab.",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    os.environ.setdefault("ORPHEUS_COMPLETION_URL", args.completion_url)
    os.environ.setdefault("SNAC_DEVICE", args.snac_device)

    # SNAC vorladen, damit die erste Anfrage nicht das Modell mitbezahlt.
    import voice_app as va

    t0 = time.perf_counter()
    va._get_snac_model(args.snac_device)
    _LOGGER.info("SNAC bereit (%s) nach %.2fs", args.snac_device, time.perf_counter() - t0)

    voices = [
        TtsVoice(
            name=name,
            description=f"Orpheus DE ({name})",
            installed=True,
            languages=["de"],
            attribution=Attribution(name="canopylabs", url="https://github.com/canopyai/Orpheus-TTS"),
            version="0.1",
        )
        for name in VOICES
    ]
    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="orpheus-de",
                description="Orpheus DE Finetune, gestreamt von der Workstation",
                attribution=Attribution(name="canopylabs", url="https://github.com/canopyai/Orpheus-TTS"),
                installed=True,
                voices=voices,
                version="0.1",
            )
        ],
    )

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Orpheus Wyoming server bereit auf %s", args.uri)
    server_task = asyncio.create_task(
        server.run(partial(OrpheusHandler, wyoming_info, args))
    )
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, server_task.cancel)
    loop.add_signal_handler(signal.SIGTERM, server_task.cancel)
    try:
        await server_task
    except asyncio.CancelledError:
        _LOGGER.info("Server gestoppt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
