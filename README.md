# LLM im Terminal mit ROCm (`/opt/rocm`)

## Standard-Workflow (Empfohlen)

Default ist jetzt: `llama-server` + `OpenCode`.

1. `llama-server` starten (Terminal A):

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./start_llama_server.sh
```

2. Im Ziel-Repo arbeiten (Terminal B):

```bash
cd /pfad/zu/deinem/repo
opencode .
```

Hinweise:
- `opencode` nutzt global standardmaessig `llama.cpp/qwen-local`.
- Default-Modell fuer `start_llama_server.sh`:
  `models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf`
- Aktueller Default-Kontext:
  `49152` (Server + OpenCode-Limit)

## TL;DR

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
# qwen3.6-27b gguf laden (optional, empfohlen)
./download_qwen36_27b.sh
# text-chat (default, ohne STT/TTS)
./chat.sh
# speech-chat (STT+TTS)
./chat.sh --mode speech

```

## Fast Start

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./download_qwen36_27b.sh

# schnell starten: Textmodus (Default)
./chat.sh

# wenn Antworten zu lange dauern: kuerzer generieren
LLAMA_N_PREDICT=120 ./chat.sh

# Sprachmodus (STT + TTS)
./chat.sh --mode speech
```

Diese Umgebung bietet dir **einen Weg**, lokal im Terminal mit einem Modell zu chatten:

- **Roh mit `llama.cpp`** (direkter Aufruf des GGUF-Modells)

## Was ist hier bereits eingerichtet?

- `llama.cpp` ist gebaut (HIP/ROCm-Backend aktiv)
- Modell liegt lokal vor: `models/Qwen3.5-9B-Q4_K_M.gguf` (Fallback)


## Voraussetzungen

- ROCm ist installiert unter `/opt/rocm`
- GPU ist unter ROCm sichtbar (`rocminfo` zeigt deine Karte)

## Quickstart

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
```

## Nutzung im Detail

## `llama.cpp` (roh)

Start mit Standardmodell:

```bash
./chat.sh
```

Modi:
- Text (Default, ohne Sprache): `./chat.sh`
- Speech (STT + TTS): `./chat.sh --mode speech`

`chat.sh` bevorzugt automatisch ein Qwen3.6-27B-GGUF in `models/`, z. B.:
- `models/Qwen3.6-27B-Q4_K_M.gguf`
- `models/Qwen3.6-27B-Instruct-Q4_K_M.gguf`

Wenn keines davon vorhanden ist, wird auf `Qwen3.5-9B-Q4_K_M.gguf` zurueckgefallen.

Start mit anderem GGUF-Modell:

```bash
./chat.sh /pfad/zu/deinem-modell.gguf
```

### Qwen3.6-27B mit llama.cpp

1. GGUF-Datei nach `models/` legen (empfohlen: `Qwen3.6-27B-Q4_K_M.gguf`).
2. Starten:

```bash
./chat.sh
```

Alternativ automatischer Download (Default: `bartowski/...-Q4_K_M`):

```bash
./download_qwen36_27b.sh
./chat.sh
```

Optionales Tuning (bei VRAM-/Speed-Bedarf):

```bash
LLAMA_CTX_SIZE=3072 LLAMA_GPU_LAYERS=80 ./chat.sh
```

Verfuegbare Parameter:
- `LLAMA_CTX_SIZE` (Default: `2048` bei 27B, sonst `4096`)
- `LLAMA_GPU_LAYERS` (Default: `40` bei 27B, sonst `99`)
- `LLAMA_THREADS` (Default: `nproc`)
- `LLAMA_N_PREDICT` (Default: `320`)
- `LLAMA_TEMP`, `LLAMA_TOP_P`

Was das Skript macht:
- setzt ROCm-Umgebung aus `/opt/rocm`
- lädt das GGUF-Modell
- startet interaktiven Chat im Terminal

## Wichtige Dateien

- `chat.sh` -> Roh-Chat mit `llama.cpp`
- `start_llama_server.sh` -> OpenAI-kompatibler `llama-server` fuer OpenCode
- `download_qwen36_27b.sh` -> laedt Qwen3.6-27B-GGUF nach `models/`
- `models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf` -> Default fuer `start_llama_server.sh`
- `models/Qwen3.6-27B-Q4_K_M.gguf` -> bevorzugtes GGUF-Modell fuer `chat.sh`
- `models/Qwen3.5-9B-Q4_K_M.gguf` -> Fallback-GGUF

## Performance-/VRAM-Tipps

- Wenn VRAM knapp wird: mit kleineren Werten starten, z. B.:
  `LLAMA_GPU_LAYERS=32 LLAMA_CTX_SIZE=1536 ./chat.sh`
- Bei RX 6700 XT ist `HSA_OVERRIDE_GFX_VERSION=10.3.0` hilfreich (bereits in Skripten gesetzt)

## Troubleshooting

### GPU wird nicht genutzt

- Prüfe ROCm:

```bash
rocminfo | sed -n '1,120p'
```

### Modell fehlt

Wenn `chat.sh` über fehlendes Modell klagt, muss die Datei hier liegen:

```text
models/Qwen3.6-27B-Q4_K_M.gguf
```

## Empfehlung

- Für maximale Kontrolle: **`./chat.sh`**
