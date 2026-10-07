import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from power.model_control import ModelControl
from power.ha_router_power import WorkstationPower


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'models').mkdir()
        for name in ('alt.gguf', 'neu.gguf'):
            (self.root / 'models' / name).touch()
        self.control = ModelControl(self.root, self.root / 'model.conf')
        self.control.props = Mock(return_value={'model_path': str(self.root / 'models/alt.gguf')})
        self.control.systemctl = Mock()
        self.control.wait_ready = Mock()

    def test_catalog_deduplicates_symlinks_and_excludes_external_files(self):
        (self.root / 'models/alias.gguf').symlink_to(self.root / 'models/alt.gguf')
        (self.root / 'extern.gguf').touch()
        (self.root / 'models/extern.gguf').symlink_to(self.root / 'extern.gguf')
        self.assertEqual(self.control.catalog(), ['alt.gguf', 'neu.gguf'])
        self.assertEqual(self.control.start('../extern.gguf')[0], 400)

    def test_success_persists_model_and_safe_context(self):
        self.control.change('neu.gguf')
        text = self.control.dropin.read_text()
        self.assertIn('neu.gguf', text)
        self.assertIn('CTX=8192', text)
        self.assertEqual(self.control.state, 'bereit')
        self.control.wait_ready.assert_called_once_with('neu.gguf')

    def test_failed_load_restores_exact_previous_configuration(self):
        previous = b'[Service]\nEnvironment="MODEL_PATH=alt.gguf"\n'
        self.control.dropin.write_bytes(previous)
        self.control.wait_ready.side_effect = [RuntimeError('Ladefehler'), None]
        self.control.change('neu.gguf')
        self.assertEqual(self.control.dropin.read_bytes(), previous)
        self.assertEqual(self.control.state, 'Fehler')
        self.assertIn('läuft wieder', self.control.error)
        self.assertEqual(self.control.wait_ready.call_args.args, ('alt.gguf',))

    def test_failed_first_change_removes_override(self):
        self.control.wait_ready.side_effect = [RuntimeError(), None]
        self.control.change('neu.gguf')
        self.assertFalse(self.control.dropin.exists())

    def test_catalog_excludes_control_characters(self):
        (self.root / 'models' / 'bad\nEnvironment=evil.gguf').touch()
        self.assertEqual(self.control.catalog(), ['alt.gguf', 'neu.gguf'])

    def test_large_model_uses_partial_gpu_offload(self):
        with open(self.root / 'models/neu.gguf', 'wb') as file:
            file.truncate(13 * 1024**3)
        self.control.change('neu.gguf')
        self.assertIn('GPU_LAYERS=20', self.control.dropin.read_text())

    def test_unknown_activity_blocks_change(self):
        with patch('power.model_control.urllib.request.urlopen', side_effect=OSError()):
            self.assertEqual(self.control.start('neu.gguf')[0], 409)
        self.control.systemctl.assert_not_called()

    def test_model_settings_merge_and_validate_whitelist(self):
        (self.root / 'profiles').mkdir()
        path = self.root / 'profiles/model-settings.json'
        path.write_text(json.dumps({'version': 1, 'defaults': {'GPU_LAYERS': 'auto',
            'LLAMA_ARG_FIT': 'on'}, 'models': {'neu.gguf': {'settings': {'CTX': 16384}}}}))
        settings = self.control.settings('neu.gguf')
        self.assertEqual(settings['CTX'], 16384)
        self.assertEqual(settings['GPU_LAYERS'], 'auto')
        self.assertEqual(settings['LLAMA_ARG_FIT'], 'on')
        path.write_text(json.dumps({'version': 1, 'defaults': {'LD_PRELOAD': 'evil'}, 'models': {}}))
        with self.assertRaisesRegex(ValueError, 'LD_PRELOAD'):
            self.control.settings('neu.gguf')

    def test_parallel_switch_rejected(self):
        self.control.state = 'lädt'
        self.assertEqual(self.control.start('neu.gguf')[0], 409)

    def test_ramona_stops_orpheus_and_returns_to_it_after_failed_load(self):
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/model-settings.json').write_text(json.dumps({
            'version': 1, 'models': {'neu.gguf': {'voice': 'ramona'}}}))
        self.control.wait_ready.side_effect = [RuntimeError('Ladefehler'), None]
        self.control.change('neu.gguf')
        calls = [call.args for call in self.control.systemctl.call_args_list]
        self.assertIn(('stop', 'wyoming-orpheus.service', 'orpheus-llm.service'), calls)
        self.assertIn(('start', 'orpheus-llm.service', 'wyoming-orpheus.service'), calls)
        self.assertLess(calls.index(('stop', 'llama-server.service')),
                        calls.index(('stop', 'wyoming-orpheus.service', 'orpheus-llm.service')))

    def test_ramona_does_not_require_stopped_orpheus_slots(self):
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/model-settings.json').write_text(json.dumps({
            'version': 1, 'models': {'alt.gguf': {'voice': 'ramona'}}}))
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock()
        with patch('power.model_control.urllib.request.urlopen', return_value=response) as opened, patch(
                'power.model_control.json.load', return_value=[{'is_processing': False}]):
            self.control.check_idle()
        self.assertEqual(opened.call_count, 1)
        self.assertIn(':8080/', opened.call_args.args[0])

    def test_busy_slot_never_restarts_service(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock()
        with patch('power.model_control.urllib.request.urlopen', return_value=response), patch(
            'power.model_control.json.load', return_value=[{'is_processing': True}]
        ):
            self.assertEqual(self.control.start('neu.gguf')[0], 409)
        self.control.systemctl.assert_not_called()

    def test_polling_offline_keeps_catalog_without_waking(self):
        power = WorkstationPower({'power_url': 'http://unused', 'token': 'test'})
        power.model_cache = {'models': ['alt.gguf'], 'active': 'alt.gguf'}
        power.wake = Mock()
        with patch('power.ha_router_power.urllib.request.urlopen', side_effect=OSError()):
            status, data = power.models()
        self.assertEqual(status, 200)
        self.assertEqual(data['models'], ['alt.gguf'])
        self.assertFalse(data['ready'])
        power.wake.assert_not_called()

    def test_switch_refused_during_router_inference(self):
        power = WorkstationPower({'power_url': 'http://unused', 'token': 'test'})
        power.active_requests = 1
        power.wake = Mock()
        self.assertEqual(power.models('neu.gguf')[0], 409)
        power.wake.assert_not_called()


if __name__ == '__main__':
    unittest.main()
