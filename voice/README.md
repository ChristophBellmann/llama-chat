# Voice-Pipeline

Schlanke Struktur mit einem Einstiegspunkt:

```text
voice/
├─ run.sh
├─ voice_app.py
├─ requirements.txt
└─ README.md
```

Standardpfad:

```text
Mikrofon -> faster-whisper -> Antwort -> Piper -> Lautsprecher
```

Optionaler Experimentpfad:

```text
Text -> Orpheus-DE -> SNAC -> Lautsprecher
```

## Setup

```bash
./voice/run.sh setup
./voice/run.sh download-piper
```

Piper testen:

```bash
./voice/run.sh tts "Die Haustür ist noch offen."
```

Voice-Loop mit Echo:

```bash
WHISPER_MODEL=small ./voice/run.sh loop --reply echo
```

Voice-Loop mit lokalem LLM-Server:

Terminal A:

```bash
./start_voice_server.sh models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

Terminal B:

```bash
LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions \
LLAMA_MODEL=voice-local \
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply llama
```

## Orpheus-Speech optional

Einmalig:

```bash
./voice/run.sh setup-orpheus
./voice/run.sh download-orpheus
```

Orpheus-TTS per `llama-completion` testen:

```bash
ORPHEUS_TTS_GPU_LAYERS=0 \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus "Die Haustür ist noch offen."
```

Orpheus-TTS über laufenden Orpheus-Server testen:

Terminal A:

```bash
MODEL="$(./voice/run.sh orpheus-path)"
PORT=8082 MODEL_ALIAS=orpheus-tts CTX=2048 GPU_LAYERS=-1 ./start_voice_server.sh "$MODEL"
```

Terminal B:

```bash
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
./voice/run.sh tts --tts orpheus-server "Die Haustür ist noch offen."
```

Falls Orpheus auf ROCm crasht, CPU erzwingen:

```bash
ORPHEUS_TTS_GPU_LAYERS=0 ./voice/run.sh tts --tts orpheus "Text"
```

## Wichtige Umgebungsvariablen

```text
WHISPER_MODEL=small|medium
WHISPER_COMPUTE_TYPE=int8
WHISPER_BEAM_SIZE=5
WHISPER_VAD=1

LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions
LLAMA_MODEL=voice-local
LLAMA_MAX_TOKENS=80
LLAMA_TEMP=0.7

PIPER_VOICE=de_DE-thorsten-medium
PIPER_MODEL=/pfad/model.onnx
PIPER_CONFIG=/pfad/model.onnx.json

ORPHEUS_TTS_MODEL=/pfad/orpheus.gguf
ORPHEUS_TTS_GPU_LAYERS=0
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion
SNAC_DEVICE=cpu|cuda
```

## Gitignore

Nicht committen:

```text
voice/.venv/
voice/models/
*.onnx
*.onnx.json
*.gguf
*.wav
```
