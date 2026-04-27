# llama-chat: lokales LLM + Voice auf ROCm

Dieses Repo bündelt drei lokale Workflows:

```text
1. Coding / OpenCode:
   llama-server -> OpenCode

2. Textchat im Terminal:
   chat.sh -> llama.cpp / llama-cli

3. Voice auf der Workstation:
   Mic -> faster-whisper -> Reply-LLM -> Orpheus-TTS -> Speaker
```

Der aktuelle Voice-Zielpfad ist:

```text
Whisper = hören
Qwen2.5 = antworten
Orpheus = sprechen
Piper = Fallback-TTS
```

Der frühere `./chat.sh --mode speech`-Pfad ist nicht mehr der Standard.

---

## 1. Standard-Workflow: OpenCode

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

## 2. Textchat im Terminal

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

# Voice Quickstart

## Zielarchitektur

```text
Mikrofon
-> faster-whisper
-> Qwen2.5-7B-Instruct non-thinking
-> Orpheus-DE TTS-Server
-> SNAC Decoder auf CPU
-> Lautsprecher
```

Dazu laufen zwei persistente `llama-server`-Instanzen:

```text
Port 8081:
  Reply-LLM
  Qwen2.5-7B-Instruct-Q4_K_M.gguf
  Aufgabe: Textantwort erzeugen

Port 8082:
  Orpheus-DE TTS
  3b-de-ft-research_release-q4_k_m.gguf
  Aufgabe: <custom_token_...> Audio-Tokens erzeugen
```

Der Voice-Loop verbindet beide Server:

```text
STT -> 8081 /v1/chat/completions -> 8082 /completion -> SNAC CPU -> Speaker
```

---

## 3. Voice Setup

Einmalig:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

./voice/run.sh setup
./voice/run.sh download-piper

./voice/run.sh setup-orpheus
./voice/run.sh download-orpheus
```

Falls das Qwen2.5-Voice-Modell noch fehlt:

```bash
mkdir -p models/voice

./voice/.venv/bin/python3 - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path
import shutil

repo = "bartowski/Qwen2.5-7B-Instruct-GGUF"
filename = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
target = Path("models/voice") / filename

path = hf_hub_download(repo_id=repo, filename=filename)
target.parent.mkdir(parents=True, exist_ok=True)

if not target.exists():
    shutil.copy2(path, target)

print(target.resolve())
print(f"{target.stat().st_size / 1024**3:.2f} GiB")
PY
```

Prüfen:

```bash
ls -lh models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf
./voice/run.sh orpheus-path
```

---

## 4. Voice Quickstart mit drei Terminals

### Terminal A: Reply-LLM starten

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

PORT=8081 \
MODEL_ALIAS=voice-local \
CTX=8192 \
GPU_LAYERS=-1 \
./start_voice_server.sh models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

Erwartung:

```text
url:   http://127.0.0.1:8081/v1
alias: voice-local
```

### Terminal B: Orpheus-TTS-Server starten

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

MODEL="$(./voice/run.sh orpheus-path)"

PORT=8082 \
MODEL_ALIAS=orpheus-tts \
CTX=2048 \
GPU_LAYERS=-1 \
./start_voice_server.sh "$MODEL"
```

Erwartung:

```text
url:   http://127.0.0.1:8082/v1
alias: orpheus-tts
```

### Terminal C: Voice-Loop starten

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

---

## 5. Einzeltests

### Reply-LLM testen

```bash
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "voice-local",
    "messages": [
      {
        "role": "system",
        "content": "Antworte kurz auf Deutsch, leicht trocken, mit gelegentlichem Kaffee-Humor."
      },
      {
        "role": "user",
        "content": "Die Haustür ist noch offen."
      }
    ],
    "max_tokens": 80,
    "temperature": 0.7,
    "stream": false
  }' | python3 -m json.tool
```

Gut ist:

```json
"content": "Dann mach sie lieber zu, bevor der Kaffee kalt wird."
```

Schlecht ist:

```json
"content": "",
"reasoning_content": "Thinking Process: ..."
```

Wenn `reasoning_content` auftaucht, läuft noch ein Thinking-Modell. Für Voice soll ein non-thinking Modell verwendet werden.

### Orpheus-TTS-Server testen

```bash
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus-server "Die Haustür ist noch offen."
```

Erwartung:

```text
Orpheus tokens: ...
Orpheus-Server: ...s Audio, sr=24000, synth=...s
```

### Piper-Fallback testen

```bash
./voice/run.sh tts --tts piper "Die Haustür ist noch offen."
```

### STT ohne LLM testen

```bash
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply echo --tts piper
```

Dieser Test prüft nur:

```text
Mikrofon -> Whisper -> erkannter Text -> Piper
```

---

## 6. Performance-orientierter Betrieb

Aktueller performanter Standard:

```text
STT:
  faster-whisper small
  CPU int8
  beam_size=5
  VAD an

Reply:
  Qwen2.5-7B-Instruct
  non-thinking
  llama-server auf Port 8081
  max_tokens=80

TTS:
  Orpheus-DE GGUF
  llama-server auf Port 8082
  /completion
  liefert <custom_token_...>

Decoder:
  SNAC
  CPU
  wird im Loop warm gehalten

Fallback:
  Piper
```

Nicht empfohlen für den produktiven Voice-Loop:

```text
- Thinking-Qwen als Reply-LLM
- Orpheus pro Satz per lokalem llama-completion neu starten
- SNAC auf ROCm/gfx1031
- Whisper tiny für deutsche Alltagssprache
```

---

## 7. Orpheus: technische Einordnung

Orpheus ist in diesem Setup **nicht STT** und nicht das normale Antwortmodell.

Orpheus übernimmt nur:

```text
Antworttext
-> Orpheus-DE
-> <custom_token_...>
-> SNAC
-> Audio
```

STT bleibt:

```text
Mikrofon-Audio -> faster-whisper -> Text
```

Antwortlogik bleibt:

```text
Text -> Qwen2.5 non-thinking -> Antworttext
```

Warum Orpheus als Server?

```text
- Das Modell bleibt geladen.
- /completion liefert schnell custom tokens.
- Der Loop muss das Orpheus-Modell nicht pro Satz neu laden.
- SNAC wird lokal auf CPU decodiert.
```

---

## 8. Verhältnis zu talk-llama.cpp / orpheus-speak Setups

Die Zielarchitektur entspricht grundsätzlich diesen lokalen Voice-Systemen:

```text
Whisper-small
-> Qwen GGUF
-> Orpheus GGUF
-> SNAC Decoder
-> Audio
```

Unterschied:

```text
Dieses Repo:
  Python-Loop
  faster-whisper
  llama-server für Reply
  llama-server für Orpheus
  SNAC CPU in Python

Optimierte C++-Setups:
  talk-llama.cpp
  whisper.cpp GGUF
  llama.cpp direkt integriert
  orpheus-speak C++ Decoder
  SNAC ONNX Runtime
  Audio direkt aus RAM
```

Unser Stand ist modularer und leichter zu debuggen.  
Der nächste Performance-Schritt wäre ein separater schneller SNAC-Decoder auf ONNX/C++-Basis.

---

## 9. Wichtige Dateien

```text
chat.sh
  Interaktiver Textchat mit llama.cpp / llama-cli.

start_llama_server.sh
  OpenAI-kompatibler llama-server für OpenCode.

start_voice_server.sh
  Generischer llama-server-Starter für Voice-Modelle.
  Wird für Reply-LLM und Orpheus-TTS verwendet.

voice/run.sh
  Einziger Einstiegspunkt für Voice:
  setup, download-piper, download-orpheus, tts, loop, orpheus-path.

voice/voice_app.py
  Enthält:
  - Aufnahme
  - STT
  - Reply-Client
  - Piper-TTS
  - Orpheus-Server-TTS
  - SNAC-Decoding
  - Voice-Loop

voice/requirements.txt
  Python-Abhängigkeiten für Voice.

voice/README.md
  Voice-spezifische Kurzbeschreibung.
```

---

## 10. Wichtige Umgebungsvariablen

### Reply-LLM

```text
LLAMA_API_URL=http://127.0.0.1:8081/v1/chat/completions
LLAMA_MODEL=voice-local
LLAMA_MAX_TOKENS=80
LLAMA_TEMP=0.7
```

### Orpheus-TTS

```text
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion
SNAC_DEVICE=cpu
```

### Whisper

```text
WHISPER_MODEL=small
WHISPER_COMPUTE_TYPE=int8
WHISPER_BEAM_SIZE=5
WHISPER_VAD=1
```

### Piper

```text
PIPER_VOICE=de_DE-thorsten-medium
PIPER_MODEL=/pfad/model.onnx
PIPER_CONFIG=/pfad/model.onnx.json
```

### Serverstart

```text
PORT=8081
MODEL_ALIAS=voice-local
CTX=8192
GPU_LAYERS=-1

PORT=8082
MODEL_ALIAS=orpheus-tts
CTX=2048
GPU_LAYERS=-1
```

---

## 11. Troubleshooting

### Voice-Loop startet, aber antwortet nicht

Erst Server prüfen:

```bash
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool
curl -s http://127.0.0.1:8082/v1/models | python3 -m json.tool
```

Dann Einzeltests aus Abschnitt 5 ausführen.

### LLM-Antwort ist leer

Prüfen, ob ein Thinking-Modell läuft:

```bash
cat /tmp/voice_last_llm_response.json | python3 -m json.tool | grep -E '"content"|"reasoning_content"|"finish_reason"' -n
```

Wenn `reasoning_content` erscheint, anderes non-thinking Modell verwenden.

### STT ist schlecht

Erst Echo-Test:

```bash
WHISPER_MODEL=small \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply echo --tts piper
```

Wenn nötig:

```bash
WHISPER_MODEL=medium \
WHISPER_COMPUTE_TYPE=int8 \
WHISPER_BEAM_SIZE=5 \
WHISPER_VAD=1 \
./voice/run.sh loop --reply echo --tts piper
```

### Orpheus-TTS crasht lokal

Nicht den lokalen `llama-completion`-Pfad verwenden.  
Der stabile Pfad ist:

```text
Orpheus als llama-server auf Port 8082
-> /completion
-> SNAC_DEVICE=cpu
```

### SNAC crasht

Immer CPU erzwingen:

```bash
SNAC_DEVICE=cpu ./voice/run.sh tts --tts orpheus-server "Text"
```

### Piper-Modell fehlt

```bash
./voice/run.sh download-piper
```

### Voice-venv fehlt

```bash
./voice/run.sh setup
```

---

## 12. Git-Hinweis

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

# TODOs

## Kurzfristig

- [ ] `start_voice_stack.sh` hinzufügen, damit Reply-LLM, Orpheus-TTS und Voice-Loop mit einem Befehl gestartet werden können.
- [ ] Prüfen, ob `./voice/run.sh loop --reply llama --tts orpheus-server` im aktuellen Stand stabil durchläuft.
- [ ] STT-Parameter final einstellen:
  - `WHISPER_MODEL=small` vs. `medium`
  - `WHISPER_BEAM_SIZE=5`
  - `WHISPER_VAD=1`
  - Aufnahme-Schwellenwerte für Start/Stop.
- [ ] Systemprompt für den Voice-Reply-Server A/B-testen:
  - kurz
  - deutsch
  - kein Markdown
  - leichter Kaffee-Humor, aber nicht übertrieben.
- [ ] README-Quickstart mit real getesteten Befehlen abgleichen.

## Mittelfristig

- [ ] Piper als automatischen Fallback behalten, falls Orpheus-TTS nicht erreichbar ist.
- [ ] Healthcheck im Loop ergänzen:
  - Port 8081 erreichbar?
  - Port 8082 erreichbar?
  - SNAC initialisiert?
- [ ] Latenz je Schritt messen und ausgeben:
  - STT-Zeit
  - Reply-Zeit
  - Orpheus-Token-Zeit
  - SNAC-Decoding-Zeit
  - Audio-Länge
  - Real-Time-Factor.
- [ ] Orpheus-TTS in 2- bis 3-Satz-Chunks unterstützen, damit längere Antworten früher abgespielt werden.
- [ ] Audio-Ausgabe entkoppeln:
  - TTS kann schon weiter decodieren, während Audio abgespielt wird.
- [ ] Konfiguration in eine `.env` oder `voice/config.env` auslagern.

## Performance / Forschung

- [ ] Python-SNAC durch ONNX Runtime Decoder ersetzen.
- [ ] Community-Decoder `snac24_dynamic_fp16` prüfen.
- [ ] Kleines `orpheus-speak`-Tool als C++/ONNX-Prozess evaluieren.
- [ ] SNAC-Decoder dauerhaft warm halten und Audio direkt aus RAM ausgeben.
- [ ] Prüfen, ob `whisper.cpp` / `talk-llama.cpp` für STT schneller oder stabiler als `faster-whisper` ist.
- [ ] `Whisper-small GGUF` mit `talk-llama.cpp` als Alternative testen.
- [ ] Gemeinsames Launcher-Script für alle Neural-Net-Komponenten bauen:
  - LLM
  - STT
  - TTS
  - Decoder.
- [ ] ROCm-Verhalten von Orpheus lokal weiter untersuchen:
  - warum lokaler `llama-completion`-Pfad instabil war
  - warum Serverpfad funktioniert
  - welche Flags relevant sind.
- [ ] Prüfen, ob SNAC auf ROCm später stabil möglich ist; aktuell Default bleibt CPU.
