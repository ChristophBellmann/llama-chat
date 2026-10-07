#!/usr/bin/env python3
"""Bereitet die Integration in einem HA-Klon vor; startet keine Dienste."""

from pathlib import Path
import shutil
import sys


def replace_once(text, old, new):
    if new in text:
        return text
    if text.count(old) != 1:
        raise RuntimeError(f"Router/Compose hat sich geändert; Stelle prüfen: {old[:70]!r}")
    return text.replace(old, new, 1)


def stage(target):
    source = Path(__file__).resolve().parent
    router_path = target / "llm-router/router.py"
    router = router_path.read_text()
    router = replace_once(router, "import uuid\n", "import uuid\n\nfrom ha_router_power import WorkstationPower, handle_power\n")
    router = replace_once(router, "        self.config = config\n",
                          "        self.config = config\n        self.workstation_power = WorkstationPower.from_environment()\n")
    router = replace_once(router, "    def do_GET(self) -> None:  # noqa: N802 - Name durch BaseHTTPRequestHandler vorgegeben\n",
                          "    def do_GET(self) -> None:  # noqa: N802 - Name durch BaseHTTPRequestHandler vorgegeben\n        if handle_power(self):\n            return\n")
    router = replace_once(router, "    def do_POST(self) -> None:  # noqa: N802 - Name durch BaseHTTPRequestHandler vorgegeben\n",
                          "    def do_POST(self) -> None:  # noqa: N802 - Name durch BaseHTTPRequestHandler vorgegeben\n        if handle_power(self):\n            return\n")
    router = replace_once(router, "    def _forward_request(self, original_body: bytes | None) -> None:\n",
                          "    def _forward_request(self, original_body: bytes | None) -> None:\n"
                          "        use_workstation = (self.command == 'POST' and\n"
                          "                           self.headers.get(TEST_BACKEND_HEADER, '').lower() != 'fallback')\n"
                          "        with self.router.workstation_power.request(use_workstation):\n"
                          "            self._forward_request_inner(original_body)\n\n"
                          "    def _forward_request_inner(self, original_body: bytes | None) -> None:\n")
    docker_path = target / "llm-router/Dockerfile"
    docker = replace_once(docker_path.read_text(), "COPY router.py /app/router.py\n",
                          "COPY router.py /app/router.py\nCOPY ha_router_power.py /app/ha_router_power.py\n")
    compose_path = target / "docker-compose.yml"
    compose = replace_once(compose_path.read_text(), "      - LLM_ROUTER_BIND=127.0.0.1:11436\n",
                           "      - LLM_ROUTER_POWER_TOKEN=${WORKSTATION_POWER_TOKEN:-}\n"
                           "      - LLM_ROUTER_BIND=127.0.0.1:11436\n")
    dashboard_path = target / "config/lovelace/sprachassistent.yaml"
    dashboard = dashboard_path.read_text()
    if "script.workstation_aufwecken" not in dashboard:
        dashboard = replace_once(dashboard, "    icon: mdi:robot-outline\n    cards:\n", "    icon: mdi:robot-outline\n    cards:\n"
            "      - type: entities\n        title: Workstation\n        show_header_toggle: false\n"
            "        entities:\n          - entity: script.workstation_aufwecken\n"
            "            name: Aufwecken\n          - entity: script.workstation_standby\n"
            "            name: Standby\n          - entity: input_boolean.workstation_automatisch_schlafen\n")
    if "select.workstation_modell" not in dashboard:
        dashboard = replace_once(dashboard,
            "          - entity: input_boolean.workstation_automatisch_schlafen\n",
            "          - entity: input_boolean.workstation_automatisch_schlafen\n"
            "          - entity: select.workstation_modell\n            name: Modell laden\n"
            "          - entity: sensor.workstation_geladenes_modell\n            name: Geladenes Modell\n"
            "          - entity: sensor.workstation_modellstatus\n            name: Modellwechsel\n")
    # Erst schreiben, nachdem alle erwarteten Stellen geprüft wurden.
    router_path.write_text(router)
    docker_path.write_text(docker)
    compose_path.write_text(compose)
    dashboard_path.write_text(dashboard)
    shutil.copyfile(source / "ha_router_power.py", target / "llm-router/ha_router_power.py")
    shutil.copyfile(source / "ha_test_router.py", target / "llm-router/tests/test_workstation_power.py")
    shutil.copyfile(source / "workstation_ha.yaml", target / "config/packages/workstation_power.yaml")
    shutil.copyfile(source / "workstation_models_ha.yaml", target / "config/packages/workstation_models.yaml")


if __name__ == "__main__":
    stage(Path(sys.argv[1]).resolve())
