import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from power import orpheus_condition


class OrpheusConditionTests(unittest.TestCase):
    def test_explicit_start_overrides_ramona_without_changing_model_configuration(self):
        control = Mock()
        with patch.object(orpheus_condition, 'manual_start_active', return_value=True):
            self.assertTrue(orpheus_condition.should_start(control))
        control.voice.assert_not_called()

    def test_automatic_start_preserves_selected_voice_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            dropin = Path(directory) / 'model.conf'
            original = b'[Service]\nEnvironment="MODEL_PATH=/models/chosen.gguf"\n'
            dropin.write_bytes(original)
            control = Mock(dropin=dropin)
            with patch.object(orpheus_condition, 'manual_start_active', return_value=False):
                for voice, expected in [('ramona', False), ('orpheus', True)]:
                    control.voice.return_value = voice
                    self.assertEqual(orpheus_condition.should_start(control), expected)
                    control.voice.assert_called_with('chosen.gguf')
            self.assertEqual(dropin.read_bytes(), original)

    def test_manual_override_requires_active_target(self):
        for code in (0, 1, 3, 4):
            with patch.object(orpheus_condition.subprocess, 'run', return_value=subprocess.CompletedProcess([], code)):
                self.assertEqual(orpheus_condition.manual_start_active(), code == 0)
        with patch.object(orpheus_condition.subprocess, 'run', side_effect=OSError):
            self.assertFalse(orpheus_condition.manual_start_active())
