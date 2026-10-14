# Neue ROCm-Umgebung für Voice vorbereiten

Der bisherige Orpheus-/SNAC-Pfad verwendet einen lokal angepassten Torch-Build
unter `/opt/rocm/wheels/pytorch_rocm711/`. Ein neuer systemweiter ROCm-Stack
erfordert auch passende Python-Pakete. Der alte Torch-Build bestand den
isolierten Test mit der neuen nativen Runtime nicht.

`voice/run.sh` unterstützt deshalb `VOICE_ROCM_RUNTIME=python-sdk` und ein
separates `VENV_DIR`. Das installiert die exakt gewählte AMD-Torch-Version mit
den passenden SDK- und `gfx1031`-Paketen. Es lädt weder das alte Wheel noch
dessen ROCm-/libomp-Pfade. Bereits eingerichtete Python-SDK-Umgebungen werden
im Modus `auto` anhand ihrer Paketmetadaten erkannt, ohne die GPU zu starten.
Die bisherige Umgebung wird dabei nicht überschrieben.

```bash
VOICE_ROCM_RUNTIME=python-sdk \
VENV_DIR=/media/christoph/some_space/Compute/ROCm/venvs/voice-10.1 \
./voice/run.sh setup-orpheus
```

Geprüfte Paketvorgabe: `torch[device-gfx1031]==2.12.0+rocm10.1.0`,
stabiler AMD-Index `https://stable.repo.amd.com/rocm/whl-next/`. Für andere
explizit geprüfte Varianten gibt es `TORCH_SDK_VERSION` und
`ROCM_DEVICE_TARGET`. Nicht ohne Geräte-/Funktionstest umstellen.

Die Installation wählt den Torch-Build über dessen vollständige Version;
der zusätzliche PyPI-Index dient gewöhnlichen Python-Abhängigkeiten.
Der abschließende Smoke-Test muss die HIP-GPU erkennen. Für die tatsächliche
SNAC-Ausführung anschließend `SNAC_DEVICE=cuda` verwenden und den vorhandenen
Offline-Streaming-Test ausführen. Die vollständige Sprachstrecke sowie LLM-
Bibliotheken werden vor dem späteren Systemwechsel separat geprüft.

Die Shell-Vertragsprüfung `tests/test_rocm_setup.py` führt das Setup mit einem
isolierten Paket-Runner aus: richtiges GPU-Paket, kein Legacy-Wheel und keine
geerbten alten Bibliothekspfade. Die GPU-/MIOpen-Tests der passenden AMD-
Torch-Pakete liegen im Wake-Word-Trainer-Vergleich. Zusätzlich bestand die
separate neue Voice-Umgebung den realen SNAC-Decoder auf der RX 6700 XT:
feste Codes, 8.192 endliche Ausgabesamples bei 24 kHz, Modellparameter auf GPU,
keine Audio-Wiedergabe. Das prüft den Decoder; die vollständige produktive
Sprachstrecke benötigt vor einer Umschaltung noch ihren eigenen Nachtest.
