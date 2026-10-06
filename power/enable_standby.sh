#!/usr/bin/env bash
set -euo pipefail
# Einmal im eigenen Terminal ausführen. Keine Passwörter in den Chat eingeben.
if [[ "$EUID" -ne 0 ]]; then
    exec sudo bash "$0" "$USER"
fi
TARGET_USER="${1:?Benutzer fehlt}"
[[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 1
TMP_RULE="$(mktemp)"
trap 'rm -f "$TMP_RULE"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl --no-block suspend\n' "$TARGET_USER" > "$TMP_RULE"
visudo -cf "$TMP_RULE"
install -o root -g root -m 440 "$TMP_RULE" /etc/sudoers.d/workstation-power
iw phy phy0 wowlan enable magic-packet
iw phy phy0 wowlan show
echo 'Standby-Rechte und aktives WoWLAN eingerichtet. Rechner bleibt eingeschaltet.'
