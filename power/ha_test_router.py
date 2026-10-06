"""Integrationstests; stage_ha.py kopiert sie zu llm-router/tests/."""

import json
import unittest
import urllib.request
from unittest.mock import Mock

from test_router import ServerContext, make_router, recording_server, server_url, unavailable_url
from ha_router_power import WorkstationPower


class WakeRouterTests(unittest.TestCase):
    def test_erste_anfrage_bleibt_nach_aufwecken_unveraendert(self):
        primary = recording_server(status=503)
        with ServerContext(primary):
            proxy = make_router(server_url(primary), unavailable_url())
            power = WorkstationPower({"wake_timeout": 1})
            power.ready = Mock(side_effect=lambda: primary.response_status == 200)
            power.send_magic_packet = Mock(side_effect=lambda: setattr(primary, "response_status", 200))
            proxy.workstation_power = power
            payload = b'{"model":"locales_llm","messages":[{"role":"user","content":"Test"}]}'
            with ServerContext(proxy):
                request = urllib.request.Request(server_url(proxy) + "/v1/chat/completions", data=payload)
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    response.read()
            power.send_magic_packet.assert_called_once()
            self.assertEqual(primary.requests[0]["body"], payload)
            self.assertEqual(power.status()["active_requests"], 0)

    def test_weckfehler_erhaelt_bisherigen_fallback(self):
        fallback = recording_server(b'{"backend":"fallback"}')
        with ServerContext(fallback):
            proxy = make_router(unavailable_url(), server_url(fallback))
            power = WorkstationPower({"wake_timeout": 0})
            power.ready = Mock(return_value=False)
            proxy.workstation_power = power
            with ServerContext(proxy):
                request = urllib.request.Request(server_url(proxy) + "/v1/chat/completions",
                    data=b'{"model":"locales_llm","messages":[]}')
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(json.load(response), {"backend": "fallback"})
            self.assertEqual(json.loads(fallback.requests[0]["body"])["model"], "qwen3.5:4b")

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
