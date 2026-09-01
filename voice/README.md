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

## NeuTTS (neurales TTS mit Voice Cloning)

Alternative zu Piper/Orpheus. Nutzt das `neuphonic/neutts-nano-german-q4-gguf`-Modell (0.2B Parameter, CPU, ~116M aktiv).

### Lokal

```bash
sudo apt install espeak-ng
pip install neutts[llama]

# Einmalig testen
export NEUTTS_REF_AUDIO=/pfad/zu/stimme.wav
./voice/run.sh tts --tts neutts "Hallo Welt"

# Oder Ordner mit mehreren Stimmen (zufällige Auswahl pro Synthese)
export NEUTTS_REF_AUDIO=/pfad/zu/stimmen/
./voice/run.sh loop --reply llama
```

Jede `.wav`-Datei im Ordner wird als eigene Stimme registriert. In HA kannst du dann bei TTS die Stimme auswählen (z. B. `voxpopuli_de_000005`).

Umgebungsvariablen:

```text
NEUTTS_REF_AUDIO   Pfad zur .wav oder Ordner mit .wav-Dateien
NEUTTS_BACKBONE    HuggingFace-Repo (default: neuphonic/neutts-nano-german-q4-gguf)
NEUTTS_CODEC       Codec-Repo (default: neuphonic/neucodec)
NEUTTS_DEVICE      cpu (default) | cuda
VOICE_TTS          neutts setzen für dauerhaften Default
```

Referenz-WAVs sollten 3–15s, mono und sauber sein. Optional `.txt`-Datei mit Transkript danebenlegen.

### Home Assistant (Docker auf thinkthing)

Ein Wyoming-Server (`wyoming-neutts`) läuft als Docker-Container im HA-Compose-Stack
und wird via Zeroconf als `tts.neutts` automatisch erkannt.
Jede `.wav` im Ordner erscheint als eigene wählbare Stimme.

```bash
# 1. .wav + Transkript (.txt) erstellen
./voice/transcribe.sh                            # alle voices/*.wav
./voice/transcribe.sh /pfad/zu/neuen/stimmen/    # beliebiger Ordner

# 2. Auf thinkthing kopieren
scp /pfad/zu/neuen/stimmen/*.{wav,txt} thinkthing:/home/christoph/home-assistant/wyoming/neutts/samples/

# 3. Container neustarten (erkennt neue Stimmen)
ssh thinkthing "docker compose -f /home/christoph/home-assistant/docker-compose.yml restart wyoming-neutts"
```

Einzelne .wav manuell:
```bash
scp stimme.wav thinkthing:/home/christoph/home-assistant/wyoming/neutts/samples/
```

Aktuelle Stimmen: `voice/*.wav` (21 VoxPopuli-Samples + greta).

### Stimme in Home Assistant ändern

**Pro Automation/Skript:** In der TTS-Aktion `tts.neutts` als Engine wählen,
dann unter "Stimme" die gewünschte Stimme aus der Dropdown-Liste auswählen
(z. B. `voxpopuli_de_000005`).

**Als Standardstimme:** In HA unter
Einstellungen → Sprachassistent → Vorzugsstimme → `neutts` → gewünschte Stimme wählen.

**Via Skript/YAML:**
```yaml
action: tts.speak
data:
  cache: true
  message: "Der Text, der vorgelesen werden soll."
  entity_id: tts.neutts
  options:
    voice: voxpopuli_de_000015
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
- Auf RX 6700 XT `HSA_OVERRIDE_GFX_VERSION=10.3.1` verwenden. `10.3.0` kann Orpheus/llama.cpp als `gfx1030` starten und instabil werden.
- `WHISPER_MODEL=small` ist ein guter erster Kompromiss. Für bessere Erkennung `medium` testen.
- `LLAMA_MAX_TOKENS=80` begrenzt Antwortlänge und Latenz.

## Orpheus-DE lokal

GPU-Server starten:

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./start_orpheus_de_server.sh
```

WAV-Datei erzeugen:

```bash
ORPHEUS_COMPLETION_URL=http://127.0.0.1:8082/completion \
SNAC_DEVICE=cpu \
./voice/run.sh tts --tts orpheus-server \
  -o /tmp/orpheus_de_test.wav \
  "Lineare Regression beschreibt den Zusammenhang zwischen Merkmalen und Zielwert."
```

Getestet: `3b-de-ft-research_release-q4_k_m.gguf`, `GPU_LAYERS=-1`, `gfx1031`, `torch==2.5.1+cpu` für SNAC.
Stimme: `jana` (Default). `julia` kennt das Finetune **nicht** -- der Name wird dann vorgelesen.

## TTS vergleichen und nachmessen

`./voice/tts_check.sh` synthetisiert, misst cold/warm getrennt, schreibt WAVs und
**transkribiert sie zurueck**. Ohne die Rueck-Transkription faellt nicht auf, wenn
ein Backend zwar Audio liefert, aber den falschen Text spricht.

```bash
./voice/tts_check.sh                                   # alle Backends, 3 Laeufe
./voice/tts_check.sh --tts piper --runs 5 "Mein Text"
./voice/tts_check.sh --tts orpheus-server --no-transcribe
```

Messung vom 01.09.2026, RX 6700 XT, SNAC auf CPU, Satz mit 4,4 s Sprechdauer:

| Backend | cold | warm | RTF warm | Text-Treue |
| --- | ---: | ---: | ---: | ---: |
| `piper` | 2,08 s | 2,43 s | 0,57 | 0,74 |
| `orpheus-server` (am Stueck) | 12,2 s | 6,66 s | 1,50 | 0,89 |
| `neutts` | -- | -- | -- | nicht installiert |

**Der Cache hilft Orpheus nicht.** Die Zeit geht zu ~78 % in die autoregressive
Token-Generierung des 3B-Modells (400-600 SNAC-Tokens pro Satz), nur ~22 % in den
SNAC-Decode. Warm ist praktisch so langsam wie cold.

## Orpheus in Echtzeit: Streaming

Am Stueck erzeugt braucht Orpheus ~6,7 s, bevor der erste Ton kommt. Der
Streaming-Pfad (`stream_orpheus_audio` + `play_audio_stream`) dekodiert dagegen
alle 7 Frames und spielt sofort ab:

| Satz | 1. Ton | gesamt | Audio | Puffer |
| --- | ---: | ---: | ---: | ---: |
| kurz (1,5-1,7 s) | 0,60-0,73 s | 1,8-2,0 s | 1,5-1,7 s | +0,18 s |
| mittel (2,8-3,7 s) | 0,60-0,62 s | 2,9-3,6 s | 2,8-3,7 s | +0,57 s |
| lang (6,7-6,8 s) | 0,61-0,62 s | 6,3-6,5 s | 6,7-6,8 s | +0,93 s |

Die Zeit bis zum ersten Ton ist unabhaengig von der Satzlaenge ~0,6 s, und der
Puffer bleibt immer positiv -- die Generierung bleibt der Wiedergabe voraus, es
gibt keine Aussetzer. Bei laengeren Saetzen waechst der Vorsprung sogar.

Streaming ist Default fuer `--tts orpheus-server`; mit `--no-stream` bekommt man
das alte Verhalten:

```bash
./start_orpheus_de_server.sh                     # Port 8082
./voice/run.sh tts --tts orpheus-server "Die Haustuer ist noch offen."
./voice/run.sh loop --reply llama --tts orpheus-server
```

Stellschrauben: `ORPHEUS_STREAM_FRAMES` (Frames pro Decode-Block, Default 7 --
kleiner = frueherer Ton, mehr CPU-Last) und das Polster in `play_audio_stream`
(Default 0,6 s).

### Was vorher gebremst hat

Zwei Einstellungen im Completion-Request waren die eigentlichen Blocker:

- `"ignore_eos": True` zwang das Modell, **immer** `n_predict` Tokens zu erzeugen,
  auch fuer einen Halbsatz. Jetzt Default aus (`ORPHEUS_IGNORE_EOS=1` schaltet es
  zurueck). Zusammen mit dem Vollformat-Prompt sank die Audiolaenge fuer denselben
  Satz von 6,1-7,3 s auf 4,1-5,0 s -- das Nachlabern am Satzende war weg.
- `"stream": False` liess den Aufrufer auf die komplette Generierung warten.

### Bekannte Einschraenkung

Das **erste Wort** einer Aeusserung ist mit diesem DE-Finetune unzuverlaessig
("Lineare" wurde als "Leere", "Lineale", "Linaere", "Die in Jahre" gesprochen).
Das tritt gestreamt wie ungestreamt auf, ist also keine Folge des Streamings.
Wer das umgehen will, stellt der Antwort ein kurzes Fuellwort voran.

## Voice-Stack: LLM + Orpheus gleichzeitig

Gemessen am 01.09.2026, beide Server parallel auf der RX 6700 XT
(`start_llama_server.sh` auf 8080, `start_orpheus_de_server.sh` auf 8082),
Orpheus belegt allein ~2,9 GiB:

| Antwort-LLM | VRAM gesamt | frei | Bewertung |
| --- | ---: | ---: | --- |
| `gemma-4-12B-it-qat` (Default) | 11,66 GiB (97 %) | 0,32 GiB | laeuft, aber ohne Reserve |
| `Qwen3.5-9B-Q4_K_M` | 10,14 GiB (85 %) | 1,85 GiB | empfohlen fuer den Voice-Stack |

Ende-zu-Ende mit gemma-4-12B, Frage rein bis erster gesprochener Ton:

| Frage | gemma | 1. Ton (TTS) | **gesamt** | Audio |
| --- | ---: | ---: | ---: | ---: |
| "Wie viele Bundeslaender hat Deutschland?" | 0,92 s | 0,75 s | **1,67 s** | 6,06 s |
| "Ist die Haustuer offen?" | 0,55 s | 0,63 s | **1,18 s** | 4,01 s |
| "Nenne einen Vorteil von Fussbodenheizung." | 0,48 s | 0,61 s | **1,10 s** | 3,84 s |

Die Rueck-Transkription bestaetigt, dass gesprochen wurde, was gemma geantwortet
hat. Keine OOM-Meldungen, das LLM blieb auch unter TTS-Last ansprechbar.

**Aber:** mit gemma-4-12B bleiben nur 0,32 GiB frei. Das reicht im Test, laesst
aber keinen Spielraum -- eine VRAM-Spitze des Desktops oder ein zweiter Slot
kann den Stack kippen. Wer LLM und TTS dauerhaft parallel faehrt, nimmt besser
Qwen3.5-9B:

```bash
PORT=8080 ./start_llama_server.sh models/Qwen3.5-9B-Q4_K_M.gguf &
./start_orpheus_de_server.sh &
```

## Orpheus als TTS in Home Assistant

Home Assistant spricht TTS ueber das Wyoming-Protokoll. Dessen Ablauf
`AudioStart` -> `AudioChunk*` -> `AudioStop` ist streamfaehig, also schreibt
`profiles/wyoming-orpheus/server.py` die Chunks raus, waehrend das Modell noch
generiert -- anders als `profiles/wyoming-neutts/server.py`, das erst komplett
synthetisiert und danach zerlegt.

Start auf der Workstation (beide Dienste noetig):

```bash
./start_orpheus_de_server.sh      # Orpheus-LLM, Port 8082, GPU
./start_wyoming_orpheus.sh        # Wyoming-TTS, Port 10401
```

In Home Assistant als Wyoming-Integration mit Host `192.168.178.51` und Port
`10401` eintragen; die Entitaet heisst dann `tts.orpheus_de`. Port 10400 ist
auf `thinkthing` schon von `wyoming-neutts` belegt, deshalb 10401.

### Gemessen am 01.09.2026

Volle Kette ueber Home Assistant, LLM und TTS beide auf der Workstation:

| Schritt | Zeit |
| --- | ---: |
| `conversation.process` gegen gemma-4-12B | 1,8-7,0 s |
| Orpheus-Synthese, erster Chunk | 0,61-0,69 s |
| Orpheus-Synthese gesamt (2,6-3,1 s Audio) | 2,8-3,0 s |

Der Server auf der Workstation protokolliert jede Synthese mit Audiolaenge,
Zeit bis zum ersten Chunk und Gesamtdauer -- das ist die verlaessliche Messung,
nicht die Zeit ueber SSH.

Home Assistant wandelt die Ausgabe selbst nach MP3 (24 kHz mono, 96 kbps) und
**cached sie**: derselbe Text loest keine zweite Synthese aus. Wer Messreihen
faehrt, variiert den Text.

### Vorsicht: das erste Wort

Die bekannte Schwaeche des DE-Finetunes wird in Home Assistant
sicherheitsrelevant. Aus gemmas Antwort "Im Bad gibt es keinen Sensor fuer die
Temperatur." machte Orpheus hoerbar "Im **Wald** gibt es keinen Sensor". Bei
Raumnamen am Satzanfang kann die Ausgabe damit das Gegenteil dessen sagen, was
gemeint war. Ein kurzes Fuellwort vor der Antwort umgeht es.

Deshalb ist `tts.orpheus_de` bewusst **nur eine zusaetzliche Entitaet** und
nicht in der Assist-Pipeline verdrahtet: produktiv bleibt Piper mit
`de_DE-ramona-low`.

### VRAM

Mit gemma-4-12B (2 Slots) und dem Orpheus-LLM zusammen: 11,66 von 11,98 GiB,
also 97 Prozent und 0,32 GiB frei. SNAC laeuft auf der CPU und kostet kein
VRAM. Fuer Dauerbetrieb ist das knapp; Qwen3.5-9B statt gemma laesst 1,85 GiB.

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
