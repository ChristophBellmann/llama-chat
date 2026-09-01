#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"
# Build-Verzeichnis. Standard ist b10741 -- zwingend fuer gemma-4 (arch "gemma4")
# und Dirk-Qwen3.8-27B (MTP-Layer). Der alte Build (Tag working-2026-03-04)
# kennt beide nicht und ist als Rueckfallebene weiter da:
#   LLAMA_BIN_DIR="$ROOT_DIR/llama.cpp/build/bin" ./run_profile.sh
BIN_DIR="${LLAMA_BIN_DIR:-$ROOT_DIR/llama.cpp-b10741/build/bin}"
PROFILES_DIR="$ROOT_DIR/profiles"
PROFILE="${1:-default}"
INI="$PROFILES_DIR/${PROFILE}.ini"

if [[ ! -x "$BIN_DIR/llama-server" ]]; then
  echo "Fehler: llama-server nicht gefunden unter $BIN_DIR/llama-server" >&2
  exit 1
fi

if [[ ! -f "$INI" ]]; then
  echo "Unbekanntes Profil: $PROFILE" >&2
  echo "Verfuegbare Profile:" >&2
  for f in "$PROFILES_DIR"/*.ini; do
    [[ -e "$f" ]] || continue
    basename "$f" .ini >&2
  done
  exit 1
fi

export LD_LIBRARY_PATH="$BIN_DIR:${LD_LIBRARY_PATH:-}"

# Ab llama.cpp b10741 werden host/port aus der ini ignoriert (der Router bindet
# sonst auf 127.0.0.1:8080). Deshalb hier explizit per CLI setzen.
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

echo "Starte llama-server mit Profil: $PROFILE"
echo "  ini:  $INI"
echo "  url:  http://$HOST:$PORT/v1"

exec "$BIN_DIR/llama-server" --models-preset "$INI" --host "$HOST" --port "$PORT"
