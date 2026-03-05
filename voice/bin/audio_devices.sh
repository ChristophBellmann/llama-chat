#!/usr/bin/env bash
set -euo pipefail

echo "=== PipeWire/PulseAudio Sources ==="
pactl list short sources || true

echo
echo "=== PipeWire/PulseAudio Sinks ==="
pactl list short sinks || true

echo
echo "=== ALSA Aufnahmegeraete (optional) ==="
arecord -L || true

echo
echo "=== ALSA Wiedergabegeraete (optional) ==="
aplay -L || true
