# LLM im Terminal mit ROCm (`/opt/rocm`)

## TL;DR

```bash
cd /media/christoph/some_space/Compute/Mogli-Lab/llama-chat
# roh mit llama.cpp
./chat.sh
# oder mit ollama
./start_ollama.sh && ./chat_ollama.sh
# ollama + datei-bridge (/read)
./chat_ollama_files.sh
```

Diese Umgebung bietet dir **zwei Wege**, lokal im Terminal mit einem Modell zu chatten:

1. **Roh mit `llama.cpp`** (direkter Aufruf des GGUF-Modells)
2. **Mit `ollama`** (komfortabler Model-Manager + Chat)

Beide Varianten sind auf deine AMD-GPU mit ROCm ausgelegt.

## Was ist hier bereits eingerichtet?

- `llama.cpp` ist gebaut (HIP/ROCm-Backend aktiv)
- Modell liegt lokal vor: `models/Qwen3.5-9B-Q4_K_M.gguf`
- `ollama` ist lokal installiert (ohne `sudo`) unter `ollama-local/`
- lokales Ollama-Modell: `qwen35-local`

## Voraussetzungen

- ROCm ist installiert unter `/opt/rocm`
- GPU ist unter ROCm sichtbar (`rocminfo` zeigt deine Karte)

## Quickstart

```bash
cd /media/christoph/some_space/Compute/Mogli-Lab/llama-chat
```

### Option A: Roh mit `llama.cpp`

```bash
./chat.sh
```

### Option B: Mit `ollama`

```bash
./start_ollama.sh
./chat_ollama.sh
```

### Option C: `ollama` + Dateilesen im Chat

```bash
./chat_ollama_files.sh
```

## Nutzung im Detail

## 1) `llama.cpp` (roh)

Start mit Standardmodell:

```bash
./chat.sh
```

Start mit anderem GGUF-Modell:

```bash
./chat.sh /pfad/zu/deinem-modell.gguf
```

Was das Skript macht:
- setzt ROCm-Umgebung aus `/opt/rocm`
- lädt das GGUF-Modell
- startet interaktiven Chat im Terminal

## 2) `ollama`

Server starten:

```bash
./start_ollama.sh
```

Chat mit lokalem Modell (`qwen35-local`):

```bash
./chat_ollama.sh
```

Mit anderem Ollama-Modell (optional):

```bash
./chat_ollama.sh qwen3.5:9b
```

Server stoppen:

```bash
./stop_ollama.sh
```

Modelle anzeigen:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 OLLAMA_MODELS=$PWD/ollama-models ./ollama-local/bin/ollama list
```

## Wichtige Dateien

- `chat.sh` -> Roh-Chat mit `llama.cpp`
- `start_ollama.sh` -> startet lokalen Ollama-Server
- `chat_ollama.sh` -> startet Chat über Ollama
- `chat_ollama_files.sh` -> Ollama-Chat mit Datei-Bridge (`/read`)
- `stop_ollama.sh` -> stoppt lokalen Ollama-Server
- `Modelfile.qwen35-local` -> Definition des lokalen Ollama-Modells
- `models/Qwen3.5-9B-Q4_K_M.gguf` -> verwendetes GGUF-Modell

## Performance-/VRAM-Tipps

- Wenn VRAM knapp wird: in `chat.sh` `--ctx-size` reduzieren (z. B. auf `2048`)
- Bei RX 6700 XT ist `HSA_OVERRIDE_GFX_VERSION=10.3.0` hilfreich (bereits in Skripten gesetzt)

## Troubleshooting

### Modell sagt: „Ich kann keine Dateien lesen“

Das ist normal für `chat_ollama.sh`. Nutze dafür:

```bash
./chat_ollama_files.sh
```

Beispiel im Chat:

```text
/read README.md
Was steht da in 3 Sätzen?
```

### Dateien schreiben im Chat

Nur in `./chat_ollama_files.sh` verfuegbar.

Beispiele:

```text
/write notes.txt
erste zeile
zweite zeile
/end
/confirm
```

```text
/append notes.txt
dritte zeile
/end
/confirm
```

```text
/replace notes.txt "zweite" "2."
/confirm
```

Sicherheit:
- Schreibaktionen werden erst als `Pending` vorbereitet.
- Erst mit `/confirm` wird wirklich geschrieben.
- Mit `/cancel` verwirfst du die Aktion.

### `ollama` kann nicht verbinden

1. Server läuft?

```bash
./start_ollama.sh
```

2. Status prüfen:

```bash
curl -s http://127.0.0.1:11434/api/tags
```

### GPU wird nicht genutzt

- Prüfe ROCm:

```bash
rocminfo | sed -n '1,120p'
```

- Prüfe Ollama-Log:

```bash
tail -n 120 ollama.log
```

### Modell fehlt

Wenn `chat.sh` über fehlendes Modell klagt, muss die Datei hier liegen:

```text
models/Qwen3.5-9B-Q4_K_M.gguf
```

## Empfehlung

- Für maximale Kontrolle: **`./chat.sh`**
- Für bequemen Alltag: **`./chat_ollama.sh`**
