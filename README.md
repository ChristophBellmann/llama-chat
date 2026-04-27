# LLM + Voice (lokal, ROCm)

Dieses Repo ist auf einen schlanken lokalen Stack ausgerichtet:

- Text-Chat: `llama.cpp` lokal
- Voice-Chat (Fast Path):
  - STT: persistenter `whisper-server`
  - LLM: persistenter `llama-server`
  - TTS: persistenter `orpheus`-Server (Voice `tara`)
  - Playback: in-memory (kein WAV-Dateihop im Hot Path)

## Quickstart

```bash
cd /media/christoph/some_space/Compute/ML-Lab/llama-chat

# 1) LLM-Server starten
./start_llama_server.sh

# 2) Textchat
./chat.sh

# 3) Voice-Chat (nutzt voice/config.yaml)
./voice/bin/voice_chat.sh
```

## Text-Chat

```bash
./chat.sh
# optional anderes GGUF
./chat.sh /pfad/zum/model.gguf
```

Optionale Tuning-Variablen:

- `LLAMA_CTX_SIZE`
- `LLAMA_GPU_LAYERS`
- `LLAMA_THREADS`
- `LLAMA_N_PREDICT`
- `LLAMA_TEMP`
- `LLAMA_TOP_P`

## Voice-Chat

Details und Konfiguration siehe:

- `README_voice.md`
- `voice/config.yaml`

## Wichtige Dateien

- `start_llama_server.sh`
- `chat.sh`
- `voice/bin/voice_chat.sh`
- `voice/bin/voice_chat_fast.py`
- `voice/config.yaml`
