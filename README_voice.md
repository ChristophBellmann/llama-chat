# Voice Chat (STT -> LLM -> TTS)

> !important
> Das ist ein alter Stand
> muss überarbeitet werden.

 
Dieses Setup baut eine lokale Sprachpipeline im Terminal:

1. Aufnahme per Push-to-talk (`pw-record`)
2. STT mit `whisper.cpp`
3. Antwort mit `llama.cpp` (`llama-cli`, **kein Ollama**)
4. TTS mit `piper`
5. Ausgabe per `pw-play`

## Dependencies

- `pipewire-utils` (liefert `pw-record`, `pw-play`)
- `ffmpeg`
- `whisper.cpp` (`whisper-cli`)
- `piper`
- `python3`
- `pyyaml`

Install-Hinweis fuer PyYAML:

```bash
pip install pyyaml
```

## Quickstart

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
./voice/bin/audio_devices.sh
# dann config anpassen
$EDITOR voice/config.yaml
./voice/bin/voice_chat.sh
```

## whisper.cpp einrichten (falls fehlt)

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat
git clone https://github.com/ggml-org/whisper.cpp third_party/whisper.cpp
cmake -S third_party/whisper.cpp -B third_party/whisper.cpp/build -G Ninja
cmake --build third_party/whisper.cpp/build -j
mkdir -p third_party/whisper.cpp/models
cd third_party/whisper.cpp/models
wget -c https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

## Konfiguration

Datei: `voice/config.yaml`

Wichtig:
- `stt.whispercpp_bin` und `stt.model_path` muessen stimmen
- `llm.bin` kann auf ein vorhandenes `llama-cli` zeigen
- `tts.piper_bin` und `tts.model_path` muessen stimmen
- `audio.backend`: `pipewire` oder `alsa`
- `audio.input_device` / `audio.output_device` optional setzen

Beispiel mit bereits funktionierendem ML-Lab ALSA-Device:

```yaml
audio:
  backend: "alsa"
  input_device: "hw:1,0"
  output_device: "hw:1,0"
  sample_rate: 16000
  channels: 1
  max_record_seconds: 12
```

Bei `pipewire` koennen `input_device`/`output_device` als Node-Name oder Serial
fuer `--target` gesetzt werden. Leer bedeutet automatische Auswahl.

## Dateien & Runtime

- Input Audio: `voice/runtime/in.wav`
- Resampled Audio: `voice/runtime/in_16k.wav`
- STT Text: `voice/runtime/in.txt`
- LLM Antwort: `voice/runtime/out.txt`
- TTS Audio: `voice/runtime/out.wav`
- Log: `voice/runtime/voice.log`

## Hinweis zu Datei-Zugriffen des LLM

Das LLM kann **nicht** selbststaendig Dateien lesen/schreiben. Es bekommt nur den Text, den diese Pipeline explizit uebergibt.
