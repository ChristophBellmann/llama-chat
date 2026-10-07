import http.client
import http.server
import threading
import unittest
from unittest.mock import Mock, patch

from power import ha_router_power, workstation_power


class PowerTests(unittest.TestCase):
    def test_magic_packet_uses_wlan_mac_and_broadcast(self):
        power = ha_router_power.WorkstationPower({"mac": "c8:b2:9b:df:73:20", "broadcast": "192.168.178.255"})
        with patch.object(ha_router_power.socket, "socket") as socket:
            power.send_magic_packet()
        packet, address = socket.return_value.__enter__.return_value.sendto.call_args.args
        self.assertEqual(packet, b"\xff" * 6 + bytes.fromhex("c8b29bdf7320") * 16)
        self.assertEqual(address, ("192.168.178.255", 9))

    def test_request_waits_until_primary_is_ready_and_counts_activity(self):
        power = ha_router_power.WorkstationPower({"wake_timeout": 4})
        power.ready = Mock(side_effect=[False, False, True])
        power.send_magic_packet = Mock()
        with patch.object(ha_router_power.time, "sleep"):
            with power.request():
                self.assertEqual(power.status()["active_requests"], 1)
                self.assertEqual(power.send_magic_packet.call_count, 2)
                self.assertEqual(power.suspend()[0], 409)
        self.assertEqual(power.status()["active_requests"], 0)

    def test_health_and_explicit_fallback_do_not_wake(self):
        power = ha_router_power.WorkstationPower({"wake_timeout": 4})
        power.wake = Mock()
        power.status()
        with power.request(False):
            pass
        power.wake.assert_not_called()

    def test_wake_timeout_preserves_forwarding_to_existing_fallback(self):
        power = ha_router_power.WorkstationPower({"wake_timeout": 0})
        power.ready = Mock(return_value=False)
        with power.request():
            self.assertEqual(power.status()["active_requests"], 1)
        self.assertEqual(power.status()["active_requests"], 0)

    def test_power_api_refuses_missing_credentials_and_busy_models(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), workstation_power.Handler)
        server.ha_host = "127.0.0.1"
        server.token = "test-token"
        server.sleep_lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(workstation_power, "activity", return_value={
                "busy": True, "reasons": ["LLM arbeitet"], "desktop_idle_seconds": 9999
            }), patch.object(workstation_power.subprocess, "run") as run:
                for headers, expected in [({}, 403), ({"Authorization": "Bearer test-token"}, 409)]:
                    connection = http.client.HTTPConnection(*server.server_address)
                    connection.request("POST", "/suspend", body=b"", headers=headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    connection.close()
                run.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_automatic_sleep_refuses_unknown_desktop_idle(self):
        # Prüfung auf der Workstation selbst: unbekanntes Desktop-Idle blockiert.
        state = {"busy": False, "reasons": [], "desktop_idle_seconds": None}
        server = Mock(ha_host="127.0.0.1", token="test-token", sleep_lock=threading.Lock())
        server.models = Mock(state="bereit", benchmark_active=False)
        handler = object.__new__(workstation_power.Handler)
        handler.server = server
        handler.client_address = ("127.0.0.1", 123)
        handler.path = "/suspend-idle"
        handler.headers = {"Authorization": "Bearer test-token"}
        handler.reply = Mock()
        with patch.object(workstation_power, "activity", return_value=state), patch.object(workstation_power.subprocess, "run") as run:
            handler.do_POST()
        self.assertEqual(handler.reply.call_args.args[0], 409)
        self.assertIn("Desktop nicht seit 30 Minuten unbenutzt", handler.reply.call_args.args[1]["reasons"])
        run.assert_not_called()

    def test_laufende_audioausgabe_verhindert_standby(self):
        gpu = Mock()
        gpu.read_text.return_value = "0"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        commands = [Mock(stdout='[{"corked":false}]'), Mock(stdout='(uint64 2000000,)')]
        with patch.object(workstation_power.urllib.request, "urlopen", return_value=response), \
             patch.object(workstation_power.json, "load", return_value=[{"is_processing": False}]), \
             patch.object(workstation_power.Path, "glob", return_value=[gpu]), \
             patch.object(workstation_power.os, "getloadavg", return_value=(0, 0, 0)), \
             patch.object(workstation_power.subprocess, "run", side_effect=commands):
            state = workstation_power.activity()
        self.assertIn("Audioausgabe läuft", state["reasons"])
        self.assertTrue(state["busy"])


if __name__ == "__main__":
    unittest.main()
