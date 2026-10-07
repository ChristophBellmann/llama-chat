#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$HOME/.config/workstation-power"
mkdir -p "$CONFIG_DIR" "$HOME/.config/systemd/user"
chmod 700 "$CONFIG_DIR"
python3 - "$CONFIG_DIR/config.json" <<'PY'
import json, pathlib, secrets, sys
path = pathlib.Path(sys.argv[1])
if not path.exists():
    path.write_text(json.dumps({"bind": "0.0.0.0", "ha_host": "192.168.178.55",
                                "token": secrets.token_urlsafe(32)}) + "\n")
path.chmod(0o600)
PY
cat > "$HOME/.config/systemd/user/workstation-power.service" <<EOF
[Unit]
Description=Standby-Steuerung durch Home Assistant
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 "$ROOT_DIR/power/workstation_power.py"
Environment=WORKSTATION_POWER_CONFIG="$CONFIG_DIR/config.json"
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
EOF
for unit in orpheus-llm wyoming-orpheus; do
  mkdir -p "$HOME/.config/systemd/user/$unit.service.d"
  cat > "$HOME/.config/systemd/user/$unit.service.d/model-voice.conf" <<EOF
[Service]
ExecCondition=/usr/bin/python3 "$ROOT_DIR/power/orpheus_condition.py"
EOF
done
systemctl --user daemon-reload
systemctl --user enable --now workstation-power.service
nmcli connection modify Ultranet 802-11-wireless.wake-on-wlan magic
echo 'Dienst und dauerhaftes WoWLAN-Profil installiert.'
echo 'Administrator-Schritt: ./power/enable_standby.sh'
