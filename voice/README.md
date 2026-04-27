# Voice-Pipeline mit lokalem LLM und Orpheus-Speech

Schlanke lokale Voice-Pipeline für das Repo `llama-chat`.

```text
Mikrofon
→ faster-whisper
→ lokaler Reply-LLM-Server
→ Orpheus-DE-TTS-Server
→ SNAC-Decoder auf CPU
→ Lautsprecher
```

Stabiler Fallback:

```text
Mikrofon
→ faster-whisper
→ lokaler Reply-LLM-Server oder Echo
→ Piper
→ Lautsprecher
```

## Schnellstart

### 1. Reply-LLM-Server starten

Terminal A:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

PORT=8081 \
MODEL_ALIAS=voice-local \
CTX=8192 \
GPU_LAYERS=-1 \
./start_voice_server.sh models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

Der Server stellt die Antwort-API bereit:

```text
http://127.0.0.1:8081/v1/chat/completions
```

### 2. Orpheus-TTS-Server starten

Terminal B:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

MODEL="$(./voice/run.sh orpheus-path)"

PORT=8082 \
MODEL_ALIAS=orpheus-tts \
CTX=2048 \
GPU_LAYERS=-1 \
./start_voice_server.sh "$MODEL"
```

Der Server stellt die Orpheus-Completion-API bereit:

```text
http://127.0.0.1:8082/completion
```

### 3. Orpheus-TTS einzeln testen

Terminal C:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus-server "Die Haustür ist noch offen."
```

Erwartung:

```text
Orpheus tokens: ...
Orpheus-Server: ...s Audio, sr=24000, synth=...s
```

### 4. Voice-Loop starten

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions \
LLAMA_MODEL=voice-local \
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
LLAMA_MAX_TOKENS=80 \
LLAMA_TEMP=0.7 \
./voice/run.sh loop --reply llama --tts orpheus-server
```

## Struktur

```text
voice/
├─ run.sh
├─ voice_app.py
├─ requirements.txt
└─ README.md
```

Ein Einstiegspunkt:

```bash
./voice/run.sh <command>
```

## Setup

Einmalig:

```bash
./voice/run.sh setup
./voice/run.sh download-piper
./voice/run.sh setup-orpheus
./voice/run.sh download-orpheus
```

## Einzeltests

### Piper-TTS

```bash
./voice/run.sh tts --tts piper "Die Haustür ist noch offen."
```

Kurzform, weil Piper Fallback/Default sein kann:

```bash
./voice/run.sh tts "Die Haustür ist noch offen."
```

### Orpheus-TTS über Server

```bash
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus-server "Die Haustür ist noch offen."
```

### Echo-Loop zum STT-Test

```bash
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply echo --tts piper
```

Damit wird vorgelesen, was Whisper verstanden hat. Das ist der schnellste Test für Mikrofon und STT.

### LLM-Loop mit Piper-Fallback

```bash
LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions \
LLAMA_MODEL=voice-local \
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply llama --tts piper
```

## Server testen

### Reply-LLM

```bash
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "voice-local",
    "messages": [
      {"role": "system", "content": "Antworte kurz auf Deutsch, leicht trocken, mit gelegentlichem Kaffee-Humor."},
      {"role": "user", "content": "Die Haustür ist noch offen."}
    ],
    "max_tokens": 80,
    "temperature": 0.7,
    "stream": false
  }' | python3 -m json.tool
```

Gut ist eine normale Antwort in:

```text
choices[0].message.content
```

Schlecht ist:

```text
content leer und reasoning_content gefüllt
```

Dann läuft ein Thinking-Modell und ist für den Voice-Loop ungünstig.

### Orpheus-TTS-Server

```bash
curl -s http://127.0.0.1:8082/completion \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "<custom_token_3><|begin_of_text|>jana: Die Haustür ist noch offen.<|eot_id|><custom_token_4><custom_token_5><custom_token_1>",
    "n_predict": 160,
    "temperature": 0.6,
    "top_p": 0.9,
    "stream": false,
    "ignore_eos": true
  }' | head -c 1200
```

Gut ist eine Folge von Tokens:

```text
<custom_token_...><custom_token_...>
```

## Betriebsarten

### Performanter Standard

```text
8081 Reply-LLM: Qwen2.5-7B-Instruct-Q4_K_M
8082 TTS:       Orpheus-DE-GGUF
SNAC:           CPU
STT:            faster-whisper small/int8
```

### Robuster Fallback

```bash
./voice/run.sh loop --reply llama --tts piper
```

### Nur STT prüfen

```bash
./voice/run.sh loop --reply echo --tts piper
```

## Wichtige Umgebungsvariablen

```text
# STT
WHISPER_MODEL=small|medium
WHISPER_COMPUTE_TYPE=int8
WHISPER_BEAM_SIZE=5
WHISPER_VAD=1

# Reply-LLM
LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions
LLAMA_MODEL=voice-local
LLAMA_MAX_TOKENS=80
LLAMA_TEMP=0.7

# Orpheus-TTS
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion
SNAC_DEVICE=cpu

# Piper-Fallback
PIPER_VOICE=de_DE-thorsten-medium
PIPER_MODEL=/pfad/model.onnx
PIPER_CONFIG=/pfad/model.onnx.json
```

## Hinweise zu Performance

- Server müssen persistent laufen. Keine Modell-Ladevorgänge im Loop.
- Orpheus-TTS über `llama-server /completion` verwenden, nicht pro Aufruf über `llama-completion` neu laden.
- `SNAC_DEVICE=cpu` gesetzt lassen. SNAC auf ROCm war instabil.
- `WHISPER_MODEL=small` ist ein guter erster Kompromiss. Für bessere Erkennung `medium` testen.
- `LLAMA_MAX_TOKENS=80` begrenzt Antwortlänge und Latenz.

## Troubleshooting

### Loop antwortet nicht

Erst beide Server testen:

```bash
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool
curl -s http://127.0.0.1:8082/v1/models | python3 -m json.tool
```

Dann TTS einzeln testen:

```bash
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus-server "Die Haustür ist noch offen."
```

### STT ist schlecht

Echo-Modus verwenden:

```bash
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply echo --tts piper
```

Bei Bedarf:

```bash
WHISPER_MODEL=medium
```

### LLM liefert leere Antwort

Dann vermutlich Thinking-Modell statt Non-Thinking-Modell. Prüfen:

```bash
cat /tmp/voice_last_llm_response.json | python3 -m json.tool | head -n 120
```

Für Voice sollte `choices[0].message.content` gefüllt sein.

### Orpheus liefert Tokens, aber es crasht danach

`SNAC_DEVICE=cpu` setzen:

```bash
SNAC_DEVICE=cpu ./voice/run.sh tts --tts orpheus-server "Text"
```

## Gitignore

Nicht committen:

```text
voice/.venv/
voice/models/
models/
*.onnx
*.onnx.json
*.gguf
*.wav
*.log
__pycache__/
*.pyc
```
