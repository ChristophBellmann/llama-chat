# Voice-Pipeline

Stabiler Standardpfad:

```text
Mikrofon -> faster-whisper -> Antwort -> Piper -> Lautsprecher
```

Orpheus ist hier bewusst nicht mehr aktiv eingebaut. Es war auf CPU zu langsam und mit ROCm/gfx1031 instabil. Fuer den produktiven Test bleibt Piper als TTS und der vorhandene `llama-server` als LLM-Antwortquelle.

## Dateien

```text
voice/
├─ run.sh            # einziger Einstiegspunkt
├─ voice_app.py      # komplette Voice-Logik
├─ requirements.txt  # Python-Abhängigkeiten
└─ README.md
```

## Setup

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./voice/run.sh setup
./voice/run.sh download-piper
```

Optional andere deutsche Stimme:

```bash
./voice/run.sh download-piper de_DE-thorsten-high
./voice/run.sh download-piper de_DE-ramona-low
```

## TTS testen

```bash
./voice/run.sh tts "Die Haustür ist noch offen."
```

## Voice Loop ohne LLM

```bash
WHISPER_MODEL=tiny ./voice/run.sh loop --reply echo
```

## Voice Loop mit lokalem LLM

Terminal A:

```bash
./start_llama_server.sh
```

Terminal B:

```bash
WHISPER_MODEL=tiny ./voice/run.sh loop --reply llama
```

Der LLM-Pfad nutzt standardmäßig:

```text
LLAMA_API_URL=http://127.0.0.1:8080/v1/chat/completions
LLAMA_MODEL=qwen-local
```

Anpassbar:

```bash
LLAMA_API_URL=http://127.0.0.1:8080/v1/chat/completions \
LLAMA_MODEL=qwen-local \
WHISPER_MODEL=tiny \
./voice/run.sh loop --reply llama
```

## Mikrofon-Schwellen

```bash
VOICE_START_RMS=0.015 VOICE_STOP_RMS=0.008 WHISPER_MODEL=tiny ./voice/run.sh loop --reply echo
```

## Gitignore

Nicht committen:

```text
voice/.venv/
voice/models/
*.onnx
*.onnx.json
*.wav
```
