import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "voice"))

import voice_app


class FakeStreamResponse:
    def __init__(self) -> None:
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self, decode_unicode=True):
        tokens = "".join(f"<custom_token_{10 + slot * 4096}>" for slot in range(7))
        yield "data: " + json.dumps({"content": tokens})
        yield "data: " + json.dumps({"stop": True})


class OrpheusStreamTest(unittest.TestCase):
    def test_long_text_is_split_without_losing_words(self) -> None:
        text = (
            "Der erste Satz ist absichtlich etwas länger. "
            "Der zweite Satz sorgt für eine weitere Grenze. "
            "Der dritte Satz beendet den Test vollständig."
        )
        segments = voice_app._split_orpheus_text(text, max_chars=70)

        self.assertGreater(len(segments), 1)
        self.assertEqual(" ".join(segments), text)
        self.assertTrue(all(len(segment) <= 70 for segment in segments))

    def test_each_segment_gets_its_own_request_with_larger_budget(self) -> None:
        payloads = []

        def fake_post(_url, json, **_kwargs):
            payloads.append(json)
            return FakeStreamResponse()

        text = "Erster vollständiger Satz. Zweiter vollständiger Satz."
        with patch.object(voice_app._HTTP, "post", side_effect=fake_post), patch.object(
            voice_app,
            "_snac_decode_frames",
            return_value=np.zeros(2048, dtype=np.float32),
        ), patch.dict(os.environ, {"ORPHEUS_STREAM_SEGMENT_CHARS": "40"}, clear=False):
            chunks = list(voice_app.stream_orpheus_audio(text))

        self.assertEqual(len(payloads), 2)
        self.assertTrue(chunks)
        self.assertTrue(
            all(p["n_predict"] == voice_app.ORPHEUS_DEFAULT_N_PREDICT for p in payloads)
        )
        self.assertTrue(all(p["ignore_eos"] is False for p in payloads))


if __name__ == "__main__":
    unittest.main()
