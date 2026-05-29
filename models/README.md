# Model files

Hier liegen die lokalen Modell-Dateien.

Hinweis:
- Die großen Modelldateien (z. B. `*.gguf`, `*.bin`, `*.safetensors`) gehoeren in diesen Ordner.
- Sie werden ueber `.gitignore` nicht mitcommittet.

## Verfügbare Modelle (GGUF)

| Modell | Größe | Quant | VRAM | Empfohlen für |
|---|---|---|---|---|
| `Qwen3.5-9B-Q4_K_M` | 5,3 GB | Q4_K_M | ~7 GB | **Default**: Multi-User, Home-Automation, Parallel-Betrieb |
| `Qwen3.6-35B-A3B-UD-IQ2_M` | 11 GB | IQ2_M (MoE) | ~12 GB | Beste Qualität, 1–2 User, knapper VRAM |
| `Qwen3-14B-Q4_K_M` | 8,4 GB | Q4_K_M | ~10 GB | Qualitäts-Alternative |
| `qwen35-4b-same-gguf-fast-Q4_K_M` | 2,7 GB | Q4_K_M | ~4 GB | Minimalistisch, schnell |
| `Loxa-3B-Q4_K_M` | 1,9 GB | Q4_K_M | ~3 GB | Voice-Fallback, einfache Tasks |
| `voice/Qwen2.5-7B-Instruct-Q4_K_M` | 4,4 GB | Q4_K_M | ~6 GB | Voice Reply-LLM (Port 8081) |

## Profile

Die Profile in `profiles/*.ini` legen fest, welches Modell mit welchen Parametern geladen wird.

```bash
./run_profile.sh              # lädt profiles/default.ini (Qwen3.5-9B)
./run_profile.sh multi-user   # identisch zu default
./run_profile.sh speed        # kurzer Kontext, schneller
./run_profile.sh stable       # größerer Kontext, stabil
./run_profile.sh longctx      # 49k Kontext (experimentell)
```
