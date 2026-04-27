# llama-chat: lokales LLM + Voice auf ROCm

Dieses Repo bündelt drei lokale Workflows:

```text
1. Coding / OpenCode:
   llama-server -> OpenCode

2. Textchat im Terminal:
   chat.sh -> llama.cpp / llama-cli

3. Voice auf der Workstation:
   Mic -> faster-whisper -> Reply Provider -> Piper -> Speaker
```

Standard für Voice ist jetzt **Piper**.  
Der frühere `./chat.sh --mode speech`-Pfad ist nicht mehr der Standard und wird nicht weiter verwendet.

---

## Standard-Workflow: OpenCode

Terminal A:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./start_llama_server.sh
```

Terminal B im Ziel-Repo:

```bash
cd /pfad/zu/deinem/repo
opencode .
```

Default:

```text
Server:      llama-server
API:         http://127.0.0.1:8080/v1
Model alias: qwen-local
Modell:      models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf
Kontext:     über start_llama_server.sh konfiguriert
```

---

## Textchat im Terminal

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./chat.sh
```

Kürzere Antworten:

```bash
LLAMA_N_PREDICT=120 ./chat.sh
```

Anderes Modell:

```bash
./chat.sh /pfad/zu/deinem-modell.gguf
```

`chat.sh` nutzt direkt:

```text
llama.cpp/build/bin/llama-cli
```

und setzt die nötige ROCm-Laufzeitumgebung script-intern.

---

## Voice: Piper als Standard

Piper ist der robuste Standardpfad für lokale Sprachausgabe:

```text
Text -> Piper -> WAV/Audio -> Speaker
```

Der Voice-Loop läuft so:

```text
Mikrofon
-> faster-whisper
-> Reply Provider
   -> echo
   -> static
   -> llama-server
-> Piper
-> Lautsprecher
```

### Setup

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./voice/setup_piper_env.sh
./voice/download_piper_de.sh
```

### TTS testen

```bash
./voice/run_tts.sh "Die Haustür ist noch offen."
```

Direkt über Piper-Wrapper:

```bash
./voice/run_tts_piper.sh "Die Haustür ist noch offen."
```

### Voice-Loop: Echo-Test

```bash
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo
```

### Voice-Loop: feste Antwort

```bash
./voice/run_voice_loop.sh --reply static
```

### Voice-Loop mit lokalem llama-server

Terminal A:

```bash
./start_llama_server.sh
```

Terminal B:

```bash
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply llama
```

---

## Orpheus: experimenteller Pfad

Orpheus bleibt im Repo als Experiment, ist aber **nicht** der Standard.

Aktueller Befund:

```text
Orpheus-DE 3B:
  CPU: zu langsam für flüssige Workstation-Voice
  ROCm/gfx1031: instabil; Crash bereits bei erstem GPU-Offload-Layer

Piper:
  stabiler Standard für lokalen Voice-Loop
```

Orpheus-TTS funktioniert technisch anders als Piper:

```text
Text
-> llama-completion erzeugt <custom_token_...>
-> SNAC decodiert Audio
-> Speaker
```

Der korrekte Raw-Completion-Aufruf braucht:

```text
llama-completion
--special
--ignore-eos
-no-cnv
--no-warmup
--flash-attn off
```

Experimenteller Test:

```bash
ORPHEUS_GPU_LAYERS=0 \
SNAC_DEVICE=cpu \
./voice/run_tts_orpheus.sh "Die Haustür ist noch offen."
```

Hinweis: Orpheus ist derzeit kein produktiver Standardpfad für dieses Setup.

---

## ROCm-Umgebung

Voraussetzungen:

```text
ROCm liegt unter /opt/rocm
llama.cpp ist mit ROCm/HIP gebaut
GPU ist über ROCm sichtbar
```

Schnelltest:

```bash
rocminfo | sed -n '1,120p'
```

Bei RX 6700 XT / gfx1031 wird in den Scripts typischerweise gesetzt:

```bash
HSA_OVERRIDE_GFX_VERSION=10.3.0
HIP_PLATFORM=amd
```

Die Startscripts setzen ihre Runtime selbst. Für normale Nutzung ist kein manuelles `source` nötig.

---

## Wichtige Dateien

```text
chat.sh
  Interaktiver Textchat mit llama.cpp / llama-cli.

start_llama_server.sh
  OpenAI-kompatibler llama-server für OpenCode.

run_opencode_local.sh
  Startet llama-server und danach OpenCode.

download_qwen36_27b.sh
  Lädt ein Qwen3.6-27B-GGUF nach models/.

voice/setup_piper_env.sh
  Richtet die Python-venv für Piper, Whisper und Audio ein.

voice/download_piper_de.sh
  Lädt das deutsche Piper-Modell.

voice/run_tts.sh
  Standard-TTS. Zeigt auf Piper.

voice/run_voice_loop.sh
  Standard-Voice-Loop. Zeigt auf Piper.

voice/run_tts_piper.sh
  Piper-TTS direkt.

voice/run_voice_loop_piper.sh
  Voice-Loop mit Piper.

voice/run_tts_orpheus.sh
  Experimenteller Orpheus-TTS-Pfad.

voice/python_rocm.sh
  Debug-Helfer für Python mit ROCm-Env.
```

---

## Modelle

### llama.cpp / Text

Bevorzugte Modelle unter `models/`:

```text
models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf
models/Qwen3.6-27B-Q4_K_M.gguf
models/Qwen3.5-9B-Q4_K_M.gguf
```

### Piper

Piper-Modelle liegen lokal unter:

```text
voice/models/
```

Diese Dateien werden nicht versioniert.

### Orpheus

Orpheus-GGUF wird aus dem Hugging-Face-Cache oder über `ORPHEUS_MODEL_PATH` genutzt.

```bash
ORPHEUS_MODEL_PATH=/pfad/zum/orpheus.gguf ./voice/run_tts_orpheus.sh "Text"
```

---

## Performance-Parameter

### Textchat

```bash
LLAMA_N_PREDICT=120 ./chat.sh
LLAMA_GPU_LAYERS=32 LLAMA_CTX_SIZE=1536 ./chat.sh
```

### Voice / Whisper

```bash
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo
WHISPER_MODEL=base ./voice/run_voice_loop.sh --reply echo
```

### Piper

```bash
PIPER_VOICE=de_DE-thorsten-medium ./voice/run_tts.sh "Text"
```

### Orpheus experimentell

```bash
ORPHEUS_GPU_LAYERS=0 SNAC_DEVICE=cpu ./voice/run_tts_orpheus.sh "Text"
```

---

## Troubleshooting

### `chat.sh --mode speech` funktioniert nicht

Der alte Speech-Modus über `chat.sh` wird nicht mehr verwendet.

Nutze stattdessen:

```bash
./voice/run_tts.sh "Die Haustür ist noch offen."
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo
```

### Piper-Modell fehlt

```bash
./voice/download_piper_de.sh
```

### Voice-venv fehlt

```bash
./voice/setup_piper_env.sh
```

### Mikrofon / Lautsprecher prüfen

```bash
./voice/python_rocm.sh - <<'PY'
import sounddevice as sd
print(sd.query_devices())
print("default:", sd.default.device)
PY
```

### llama-server-Modell fehlt

Wenn `start_llama_server.sh` über ein fehlendes Modell klagt, prüfe:

```bash
ls -lah models/
```

oder starte mit explizitem Modell:

```bash
./start_llama_server.sh /pfad/zum/model.gguf
```

### GPU wird nicht genutzt

```bash
rocminfo | sed -n '1,120p'
```

Bei VRAM-Problemen:

```bash
LLAMA_GPU_LAYERS=32 LLAMA_CTX_SIZE=1536 ./chat.sh
```

---

## Git-Hinweis

Committen:

```text
*.sh
*.py
*.md
requirements*.txt
```

Nicht committen:

```text
voice/.venv/
voice/models/
voice/cache/
voice/output/
voice/tmp/
*.gguf
*.onnx
*.onnx.json
*.wav
*.mp3
*.log
__pycache__/
```

Empfohlene `.gitignore`-Einträge:

```gitignore
voice/.venv/
voice/models/
voice/cache/
voice/output/
voice/tmp/
voice/*.wav
voice/*.onnx
voice/*.onnx.json
voice/*.log
voice/__pycache__/
voice/**/*.pyc

*.gguf
*.onnx
*.onnx.json
*.wav
*.mp3
*.log

__pycache__/
*.py[cod]
.venv/
venv/
```

---

## Empfehlung

```text
Coding:
  ./start_llama_server.sh
  opencode .

Textchat:
  ./chat.sh

Voice:
  ./voice/run_tts.sh "Text"
  WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo

Orpheus:
  nur experimentell
```
