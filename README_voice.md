# Voice Chat (Fast Path: STT -> LLM -> TTS)

Die Voice-Pipeline ist auf Performance optimiert:

1. Aufnahme (Push-to-talk)
2. STT ueber persistenten `whisper-server`
3. Antwort ueber persistenten `llama-server`
4. TTS ueber persistenten `orpheus`-Server (Voice `tara`)
5. Playback in-memory ueber `pw-play`/`aplay`

## Dependencies

- `pipewire-utils` (`pw-record`, `pw-play`) oder ALSA (`arecord`, `aplay`)
- `python3`
- `pyyaml`
- laufender `whisper-server`
- laufender `llama-server`
- laufender `orpheus`-TTS-Server (OpenAI-kompatibel)

## Start

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

# LLM-Server
./start_llama_server.sh

# Whisper- und Orpheus-Server separat starten
# (abhängig von deiner lokalen Installation)

# Audio-Devices checken, Config anpassen, Voice-Loop starten
./voice/bin/audio_devices.sh
$EDITOR voice/config.yaml
./voice/bin/voice_chat.sh
```

## Konfiguration

Datei: `voice/config.yaml`

Wichtige Felder:

- `audio.backend: pipewire|alsa`
- `audio.input_device`, `audio.output_device`
- `stt.server_url`
- `llm.base_url`, `llm.model_alias`
- `tts.base_url`, `tts.model`, `tts.voice` (Standard: `tara`)

## Runtime

- Hot Path arbeitet ohne verpflichtende Audio/Text-Dateihops.
- Log: `voice/runtime/voice.log`
