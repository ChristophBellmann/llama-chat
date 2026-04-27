# Voice Folder

Default path: Piper.

## Setup

```bash
./voice/setup_piper_env.sh
./voice/download_piper_de.sh
```

## TTS

```bash
./voice/run_tts.sh "Die Haustür ist noch offen."
```

Equivalent:

```bash
./voice/run_tts_piper.sh "Die Haustür ist noch offen."
```

## Voice loop

```bash
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo
```

With local llama-server as answer generator:

```bash
./start_llama_server.sh
WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply llama
```

## Orpheus experiment

Orpheus-DE 3B is not the default.

Current finding:
- CPU is too slow.
- ROCm/gfx1031 crashes during first decode even with small context, no warmup, flash-attn off.
- Keep Orpheus as experiment only.

```bash
./voice/setup_voice_env.sh
./voice/download_orpheus_de.sh
ORPHEUS_GPU_LAYERS=0 SNAC_DEVICE=cpu ./voice/run_tts_orpheus.sh "Die Haustür ist noch offen."
```
