#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$ROOT_DIR/llama.cpp/build/bin"
PROFILES_DIR="$ROOT_DIR/profiles"
PROFILE="${1:-stable}"
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

echo "Starte llama-server mit Profil: $PROFILE"
echo "  ini: $INI"

exec "$BIN_DIR/llama-server" --models-preset "$INI"
