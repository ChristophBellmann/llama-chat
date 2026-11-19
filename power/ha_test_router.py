"""Integrationstests; stage_ha.py kopiert sie zu llm-router/tests/."""

import json
import time
import unittest
import urllib.request
from unittest.mock import Mock

from test_router import ServerContext, make_router, recording_server, server_url, unavailable_url
from ha_router_power import WorkstationPower


class WakeRouterTests(unittest.TestCase):
    def test_explizites_aufwecken_und_anschiessende_anfrage_bleiben_erhalten(self):
        primary = recording_server(status=503)
        with ServerContext(primary):
            proxy = make_router(server_url(primary), unavailable_url())
            power = WorkstationPower({"wake_timeout": 1})
            power.ready = Mock(side_effect=lambda: primary.response_status == 200)
            power.send_magic_packet = Mock(side_effect=lambda: setattr(primary, "response_status", 200))
            proxy.workstation_power = power
            payload = b'{"model":"locales_llm","messages":[{"role":"user","content":"Test"}]}'
            with ServerContext(proxy):
                with urllib.request.urlopen(urllib.request.Request(
                        server_url(proxy) + "/workstation/wake", data=b""), timeout=3) as response:
                    self.assertTrue(json.load(response)["ready"])
                request = urllib.request.Request(server_url(proxy) + "/v1/chat/completions", data=payload)
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    response.read()
            power.send_magic_packet.assert_called_once()
            self.assertEqual(primary.requests[0]["body"], payload)
            self.assertEqual(power.status()["active_requests"], 0)

    def test_ordinary_voice_uses_fallback_without_wake_or_network_status(self):
        fallback = recording_server(b'{"backend":"fallback"}')
        with ServerContext(fallback):
            proxy = make_router(unavailable_url(), server_url(fallback))
            power = WorkstationPower({"wake_timeout": 0})
            power.wake = Mock(side_effect=AssertionError("Kein Aufwecken für Voice"))
            power.benchmark = Mock(side_effect=AssertionError("Keine Netzprüfung für Voice"))
            proxy.workstation_power = power
            with ServerContext(proxy):
                request = urllib.request.Request(server_url(proxy) + "/v1/chat/completions",
                    data=b'{"model":"locales_llm","messages":[]}')
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(json.load(response), {"backend": "fallback"})
            self.assertEqual(json.loads(fallback.requests[0]["body"])["model"], "qwen3.5:4b")

    def test_nach_weckfehler_wartet_naechste_anfrage_nicht_erneut(self):
        power = WorkstationPower({"wake_timeout": 0.3, "wake_retry_after": 60})
        power.ready = Mock(return_value=False)
        power.send_magic_packet = Mock()
        self.assertFalse(power.wake())
        versuche = power.send_magic_packet.call_count
        self.assertGreater(versuche, 0)
        start = time.monotonic()
        self.assertFalse(power.wake())
        self.assertLess(time.monotonic() - start, 0.1)
        self.assertEqual(power.send_magic_packet.call_count, versuche)
        # Ist die Workstation wieder da, gilt das sofort.
        power.ready = Mock(return_value=True)
        self.assertTrue(power.wake())
        self.assertEqual(power.wake_failed_until, 0.0)

    def test_weckversuch_nach_sperrzeit_wieder_moeglich(self):
        power = WorkstationPower({"wake_timeout": 0, "wake_retry_after": 0})
        power.ready = Mock(return_value=False)
        power.send_magic_packet = Mock()
        power.wake()
        power.config["wake_timeout"] = 0.1
        power.wake()
        power.send_magic_packet.assert_called()

    def test_modellliste_weckt_nicht_auf(self):
        primary = recording_server()
        with ServerContext(primary):
            proxy = make_router(server_url(primary), unavailable_url())
            power = WorkstationPower({"wake_timeout": 1})
            power.wake = Mock()
            proxy.workstation_power = power
            with ServerContext(proxy):
                with urllib.request.urlopen(server_url(proxy) + "/v1/models", timeout=3) as response:
                    response.read()
            power.wake.assert_not_called()

class ModelRouterTests(unittest.TestCase):
    def test_modellwechsel_body_wird_geprueft_und_weitergegeben(self):
        proxy = make_router(unavailable_url(), unavailable_url())
        proxy.workstation_power.models = Mock(return_value=(202, {'status': 'lädt'}))
        with ServerContext(proxy):
            request = urllib.request.Request(server_url(proxy) + '/workstation/models',
                data=b'{"model":"test.gguf"}', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.load(response)['status'], 'lädt')
        proxy.workstation_power.models.assert_called_once_with('test.gguf')

    def test_ungueltiger_modellwechsel_wird_abgewiesen(self):
        proxy = make_router(unavailable_url(), unavailable_url())
        proxy.workstation_power.models = Mock()
        with ServerContext(proxy):
            request = urllib.request.Request(server_url(proxy) + '/workstation/models', data=b'{"model":42}')
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        proxy.workstation_power.models.assert_not_called()


class BenchmarkRouterTests(unittest.TestCase):
    def test_benchmark_nutzt_fallback_statt_testmodell(self):
        primary = recording_server(b'{"backend":"primary"}')
        fallback = recording_server(b'{"backend":"fallback"}')
        with ServerContext(primary), ServerContext(fallback):
            proxy = make_router(server_url(primary), server_url(fallback))
            power = WorkstationPower({'power_url': 'http://unused', 'token': 'test'})
            power.benchmark_cache = {'status': 'läuft'}
            power.wake = Mock()
            proxy.workstation_power = power
            with ServerContext(proxy):
                request = urllib.request.Request(server_url(proxy) + '/v1/chat/completions',
                    data=b'{"model":"locales_llm","messages":[]}')
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(json.load(response), {'backend': 'fallback'})
            self.assertFalse(primary.requests)
            power.wake.assert_not_called()
            self.assertEqual(json.loads(fallback.requests[0]['body'])['model'], 'qwen3.5:4b')

    def test_erzwungener_primary_im_benchmark_wird_abgewiesen(self):
        proxy = make_router(unavailable_url(), unavailable_url())
        power = WorkstationPower({'power_url': 'http://unused', 'token': 'test'})
        power.benchmark_cache = {'status': 'läuft'}
        proxy.workstation_power = power
        with ServerContext(proxy):
            request = urllib.request.Request(server_url(proxy) + '/v1/chat/completions',
                data=b'{}', headers={'X-LLM-Router-Backend': 'primary'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(error.exception.code, 503)
            error.exception.close()

    def test_startet_benchmark_mit_optionaler_modellliste(self):
        proxy = make_router(unavailable_url(), unavailable_url())
        proxy.workstation_power.benchmark = Mock(return_value=(202, {'status': 'läuft'}))
        with ServerContext(proxy):
            request = urllib.request.Request(server_url(proxy) + '/workstation/benchmark',
                data=b'{"models":["test.gguf"]}')
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
        proxy.workstation_power.benchmark.assert_called_once_with('start', ['test.gguf'])
