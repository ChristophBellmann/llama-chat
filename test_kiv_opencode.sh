#!/usr/bin/env bash
set -euo pipefail

PORT="${KIV_PORT:-11435}"
MODEL="${KIV_MODEL_ID:-google/gemma-4-E2B-it}"

curl -fsS "http://127.0.0.1:${PORT}/api/version" >/dev/null

echo "OpenCode models for provider kiv:"
opencode models kiv

echo
echo "OpenCode one-shot run on kiv/$MODEL:"
opencode run -m "kiv/${MODEL}" "Antworte exakt mit KIV_OK"
