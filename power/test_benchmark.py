import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from power.model_benchmark import ModelBenchmark, measure
from power.model_control import ModelControl


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'models').mkdir()
        for model in ('alt.gguf', 'neu.gguf'):
            (self.root / 'models' / model).touch()
        self.control = ModelControl(self.root, self.root / 'model.conf')
        self.control.dropin.write_bytes(b'vorherige Einstellungen')
        self.control.props = Mock(return_value={'model_path': 'alt.gguf'})
        self.control.check_idle = Mock()
        self.control.systemctl = Mock()
        self.control.wait_ready = Mock()
        self.bench = ModelBenchmark(self.control, self.root / 'benchmark.json')

    def test_failed_model_continues_and_restores_exact_configuration(self):
        previous = self.control.dropin.read_bytes()
        def change(model):
            self.control.dropin.write_bytes(b'andere Einstellung')
            self.control.props.return_value = {'model_path': model}
            self.control.state = 'Fehler' if model == 'neu.gguf' else 'bereit'
        self.control.change = change
        sample = {'ttft_s': 0.5, 'total_s': 2, 'tokens_s': 20, 'tokens': 40}
        with patch('power.model_benchmark.gpu_memory', return_value={'used_mib': 1000, 'total_mib': 12000}), patch(
                'power.model_benchmark.measure', return_value=sample) as measured:
            self.bench.run(['neu.gguf', 'alt.gguf'], 'alt.gguf', previous)
        self.assertEqual(measured.call_count, 5)
        self.assertEqual(self.control.dropin.read_bytes(), previous)
        self.assertEqual(self.bench.data['status'], 'fertig mit Fehlern')
        self.assertTrue(self.bench.data['restored'])
        self.assertFalse(self.control.benchmark_active)
        self.assertEqual(self.bench.data['results'][1]['ttft_s'], 0.5)
        self.control.wait_ready.assert_called_once_with('alt.gguf')

    def test_cancellation_restores_original_without_measuring(self):
        self.bench.cancel.set()
        with patch('power.model_benchmark.measure') as measured:
            self.bench.run(['neu.gguf'], 'alt.gguf', None)
        measured.assert_not_called()
        self.assertFalse(self.control.dropin.exists())
        self.assertEqual(self.bench.data['status'], 'abgebrochen')

    def test_manual_change_and_second_run_blocked_while_benchmark_active(self):
        self.control.benchmark_active = True
        self.assertEqual(self.control.start('neu.gguf')[0], 409)
        self.assertEqual(self.bench.start()[0], 409)

    def test_invalid_model_list_never_starts_worker(self):
        with patch('power.model_benchmark.threading.Thread') as thread:
            for models in ([], 'alt.gguf', ['../extern.gguf'], [42]):
                self.assertEqual(self.bench.start(models)[0], 400)
            thread.assert_not_called()

    def test_stream_ignores_role_chunks_and_reports_generation_timings(self):
        response = Mock(status=200)
        chunks = [{'choices': [{'delta': {'role': 'assistant'}}]},
                  {'choices': [{'delta': {'content': 'Test'}}]},
                  {'choices': [], 'usage': {'completion_tokens': 20},
                   'timings': {'predicted_per_second': 40}}]
        response.readline.side_effect = [b'data: ' + json.dumps(c).encode() + b'\n' for c in chunks] + [b'data: [DONE]\n']
        connection = Mock()
        connection.getresponse.return_value = response
        with patch('power.model_benchmark.http.client.HTTPConnection', return_value=connection):
            result = measure(threading.Event())
        self.assertEqual(result['tokens_s'], 40)
        self.assertEqual(result['tokens'], 20)
        self.assertIsNotNone(result['ttft_s'])
        connection.close.assert_called_once()

    def test_incomplete_stream_is_an_error(self):
        response = Mock(status=200)
        response.readline.return_value = b''
        connection = Mock()
        connection.getresponse.return_value = response
        with patch('power.model_benchmark.http.client.HTTPConnection', return_value=connection):
            with self.assertRaisesRegex(RuntimeError, 'vollständige'):
                measure(threading.Event())

    def test_async_job_streams_http_results_and_releases_reservation(self):
        import http.client
        import http.server
        import time
        original_connection = http.client.HTTPConnection
        class Handler(http.server.BaseHTTPRequestHandler):
            requests = 0
            def log_message(self, *_args):
                pass
            def do_POST(self):
                type(self).requests += 1
                self.rfile.read(int(self.headers['Content-Length']))
                body = ('data: {"choices":[{"delta":{"content":"Test"}}]}\n\n'
                        'data: {"choices":[],"usage":{"completion_tokens":20},'
                        '"timings":{"predicted_per_second":40}}\n\n'
                        'data: [DONE]\n\n').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        previous = self.control.dropin.read_bytes()
        def change(model):
            self.control.dropin.write_bytes(model.encode())
            self.control.props.return_value = {'model_path': model}
            self.control.state = 'bereit'
        self.control.change = change
        self.control.wait_ready.side_effect = lambda model: setattr(self.control.props, 'return_value', {'model_path': model})
        with patch('power.model_benchmark.http.client.HTTPConnection',
                   side_effect=lambda _host, _port, timeout: original_connection(*server.server_address, timeout=timeout)), patch(
                'power.model_benchmark.gpu_memory', return_value={'used_mib': 1000, 'total_mib': 12000}):
            code, _ = self.bench.start(['alt.gguf', 'neu.gguf'])
            self.assertEqual(code, 202)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self.bench.status()['status'] in ('läuft', 'stellt wieder her'):
                time.sleep(0.01)
        result = self.bench.status()
        self.assertEqual(result['status'], 'fertig', result)
        self.assertEqual(Handler.requests, 10)
        self.assertEqual(result['completed'], 2)
        self.assertEqual(result['results'][1]['tokens_s'], 40)
        self.assertEqual(self.control.dropin.read_bytes(), previous)
        self.assertFalse(self.control.benchmark_active)
        self.assertFalse(self.bench.recovery.exists())

    def test_unwritable_output_never_reserves_or_changes_model(self):
        self.control.change = Mock()
        with patch('power.model_benchmark.gpu_memory', return_value={'used_mib': 1000, 'total_mib': 12000}), patch.object(
                self.bench, 'publish', side_effect=OSError('Ablage voll')):
            self.assertEqual(self.bench.start()[0], 503)
        self.assertFalse(self.control.benchmark_active)
        self.control.change.assert_not_called()

    def test_result_write_failure_cannot_prevent_restoration(self):
        previous = self.control.dropin.read_bytes()
        self.control.dropin.write_bytes(b'anderes Modell')
        with patch.object(self.bench, 'publish', side_effect=OSError('Ablage voll')):
            self.bench.run([], 'alt.gguf', previous)
        self.assertEqual(self.control.dropin.read_bytes(), previous)
        self.control.wait_ready.assert_called_once_with('alt.gguf')
        self.assertFalse(self.control.benchmark_active)
        self.assertTrue(self.bench.data['restored'])

    def test_restart_recovers_saved_settings(self):
        import base64
        saved = self.control.dropin.read_bytes()
        self.bench.recovery.write_text(json.dumps({'model': 'alt.gguf',
            'configuration': base64.b64encode(saved).decode()}))
        self.control.dropin.write_bytes(b'anderes Modell')
        with patch('power.model_benchmark.threading.Thread') as thread:
            recovered = ModelBenchmark(self.control, self.bench.output)
        self.assertTrue(self.control.benchmark_active)
        self.assertTrue(recovered.cancel.is_set())
        self.assertEqual(thread.call_args.kwargs['args'], ([], 'alt.gguf', saved))
        recovered.run([], 'alt.gguf', saved)
        self.assertEqual(self.control.dropin.read_bytes(), saved)
        self.assertFalse(recovered.recovery.exists())


if __name__ == '__main__':
    unittest.main()
