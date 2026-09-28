from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import AsyncMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


class _Info:
    def event(self):
        return None


class OrpheusHandlerTest(unittest.IsolatedAsyncioTestCase):
    def handler(self) -> server.OrpheusHandler:
        args = SimpleNamespace(
            voice="jana",
            samples_per_chunk=1024,
            tail_silence_ms=0,
            max_audio_seconds=0,
        )
        handler = server.OrpheusHandler(_Info(), args, None, None)
        handler.write_event = AsyncMock()
        return handler

    async def test_normaler_abschnitt_bricht_streaming_sitzung_nicht_ab(self):
        handler = self.handler()

        def stream_orpheus_audio(*_args, **_kwargs):
            yield 24000, np.zeros(2048, dtype=np.float32)

        fake_voice_app = SimpleNamespace(stream_orpheus_audio=stream_orpheus_audio)
        vorher = sys.modules.get("voice_app")
        sys.modules["voice_app"] = fake_voice_app
        try:
            await handler._spreche("Ein vollständiger Abschnitt.", "jana")
            self.assertFalse(handler._cancel_event.is_set())
            await handler._spreche("Auch dieser Abschnitt muss folgen.", "jana")
            self.assertFalse(handler._cancel_event.is_set())
            self.assertEqual(handler._stream_samples, 4096)
        finally:
            if vorher is None:
                sys.modules.pop("voice_app", None)
            else:
                sys.modules["voice_app"] = vorher

    async def test_expliziter_abbruch_setzt_merker(self):
        handler = self.handler()
        handler._active_response["response"] = SimpleNamespace(close=unittest.mock.Mock())
        handler._cancel_stream()
        self.assertTrue(handler._cancel_event.is_set())
        handler._active_response["response"].close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
