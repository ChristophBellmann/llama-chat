# Model files

Hier liegen die lokalen Modell-Dateien.

Hinweis:
- Die großen Modelldateien (z. B. `*.gguf`, `*.bin`, `*.safetensors`) gehoeren in diesen Ordner.
- Sie werden ueber `.gitignore` nicht mitcommittet.

## Verfügbare Modelle (GGUF)

| Modell | Größe | Quant | VRAM | Empfohlen für |
|---|---|---|---|---|
| `gemma-4-12B-it-qat-UD-Q4_K_XL` | 6,2 GB | Q4_0 (QAT) | 8,2 GB | **Default**: Textchat, Home-Automation |
| `Qwen3.5-9B-Q4_K_M` | 5,3 GB | Q4_K_M | 6,5 GB | Schnellste Alternative, groesste VRAM-Reserve |
| `Dirk-Qwen3.8-27B-UD-IQ3_XXS` | 10,2 GB | IQ3_XXS | 11,5 GB | Nur mit llama.cpp >= b10741, VRAM zu 96 % voll |
| `Qwen3.6-35B-A3B-UD-IQ2_M` | 11 GB | IQ2_M (MoE) | ~12 GB | Beste Qualität, 1–2 User, knapper VRAM |
| `Qwen3-14B-Q4_K_M` | 8,4 GB | Q4_K_M | ~10 GB | Qualitäts-Alternative |
| `qwen35-4b-same-gguf-fast-Q4_K_M` | 2,7 GB | Q4_K_M | ~4 GB | Minimalistisch, schnell |
| `Loxa-3B-Q4_K_M` | 1,9 GB | Q4_K_M | ~3 GB | Voice-Fallback, einfache Tasks |
| `voice/Qwen2.5-7B-Instruct-Q4_K_M` | 4,4 GB | Q4_K_M | ~6 GB | Voice Reply-LLM (Port 8081) |

## Thinking / Reaktionszeit

**Alle** aktuell genutzten Modelle haben `enable_thinking` im Chat-Template --
auch gemma-4. Ohne Gegenmassnahme denkt das Modell vor jeder Antwort.

**`--reasoning-budget 0` reicht nicht.** Gemessen auf b10741 mit
`Qwen3.5-9B-Q4_K_M`: mit und ohne das Flag identisch 5,2 s, und bei
`max_tokens 200` kommt der `content` sogar **leer** zurueck, weil das komplette
Budget im Denken aufgeht. Bei gemma-4 greift das Flag, bei den qwen35-Modellen
nicht.

Der Schalter, der zuverlaessig wirkt, ist `chat-template-kwargs`:

```
chat-template-kwargs = {"enable_thinking":false}
```

Gleiche Frage, gleiches Modell: **0,39 s statt 5,2 s**, 12 statt 250 Tokens.
Der Key steht in allen Profilen (`default`, `multi-user`, `speed`, `stable`,
`longctx`) unter `[*]` und gilt damit fuer alle Modelle; `start_llama_server.sh`
(der Pfad der systemd-Unit) setzt ihn ueber `CHAT_TEMPLATE_KWARGS`. Er funktioniert sowohl per CLI als auch aus der ini -- die frueher
hier stehende Behauptung, die Profile kennten keinen Thinking-Schalter, war
falsch (unbekannte Keys brechen mit `option '...' not recognized in preset`
ab; `chat-template-kwargs` wird akzeptiert).

## Textchat-Benchmark (kleiner Kontext)

Gemessen am 01.09.2026 auf der RX 6700 XT (11,98 GiB), llama.cpp **b10741**,
`ctx 8192`, `parallel 1`, `-fa on`, KV `q8_0`, Thinking via
`chat-template-kwargs` aus. Durchsatz aus `llama-bench`, Zeiten sind echte
Server-Roundtrips auf deutsche Kurzfragen.

| Modell | Datei | pp512 | tg128 | VRAM belegt | kurze Antwort | ~70-Token-Antwort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Qwen3.5-9B-Q4_K_M` | 5,28 GiB | **849 t/s** | **50,2 t/s** | 6,52 GiB | **0,38 s** | **1,64 s** |
| `gemma-4-12B-it-qat-UD-Q4_K_XL` | 6,24 GiB | 838 t/s | 39,5 t/s | 8,18 GiB | 0,41 s | 1,95 s |
| `Dirk-Qwen3.8-27B-UD-IQ3_XXS` | 10,17 GiB | 287 t/s | 18,7 t/s | 11,49 GiB | 1,74 s | 4,51 s |

**Ergebnis:** Reiner Durchsatzsieger ist `Qwen3.5-9B-Q4_K_M` (beim Generieren
27 % schneller als gemma-4-12B, 2,7x schneller als das 27B, groesste
VRAM-Reserve). Als Default eingestellt ist trotzdem
`gemma-4-12B-it-qat-UD-Q4_K_XL`: der Latenzunterschied ist im Textchat mit
kleinem Kontext klein (0,41 s vs. 0,38 s kurze Antwort, 1,95 s vs. 1,64 s bei
~70 Tokens), und das Deutsch war im Test die runde Formulierung wert. Mit
8,18 GiB bleiben ~3,8 GiB Reserve -- genug fuer `parallel = 2`, aber weniger
Luft als bei Qwen3.5-9B.

In `default.ini` steht bewusst `parallel = 1` und `ctx-size = 8192`: gemessen
wurde Einzelnutzer-Textchat mit kleinem Kontext, und ein Slot bekommt so den
vollen Kontext. Fuer Mehrbenutzerbetrieb `parallel = 2` setzen -- der VRAM
reicht dafuer nur bei Qwen3.5-9B und gemma-4-12B, nicht beim 27B.

`Qwen3.5-9B-Q4_K_M` ist die Alternative, wenn Latenz oder VRAM-Reserve wichtiger
werden als die Formulierung -- Umschalten in `profiles/default.ini`, sonst
aendert sich nichts.

Inhaltlich waren alle drei auf den Testfragen korrekt.

## llama.cpp b10741 ist jetzt der Standard-Build

Der alte Build (`24d2ee052`, 2026-03-04, getaggt als `working-2026-03-04`) kann
**zwei der drei** Modelle nicht laden:

| Modell | alter Build | Fehler |
| --- | --- | --- |
| `gemma-4-12B-it-qat-UD-Q4_K_XL` | nein | `unknown model architecture: 'gemma4'` |
| `Dirk-Qwen3.8-27B-UD-IQ3_XXS` | nein | `missing tensor 'blk.64.ssm_conv1d.weight'` |
| `Qwen3.5-9B-Q4_K_M` | ja | -- |

`run_profile.sh` und `start_llama_server.sh` zeigen deshalb standardmaessig auf
`llama.cpp-b10741/build/bin`. Rueckfall auf den alten Build (dann nur mit
Qwen3.5-9B):

```bash
LLAMA_BIN_DIR="$PWD/llama.cpp/build/bin" ./run_profile.sh
```

## Dirk-Qwen3.8-27B: der MTP-Layer

Mit dem alten Build laedt das Modell gar nicht:

```
llama_model_load: error loading model: missing tensor 'blk.64.ssm_conv1d.weight'
```

Das Modell ist arch `qwen35` (Hybrid: SSM-Layer, jeder 4. Layer echte
Attention) und hat `nextn_predict_layers = 1`, d.h. `blk.64` ist ein
MTP-Head. Der dense-qwen35-Loader lief stur ueber alle 65 Bloecke und hielt
`blk.64` fuer einen SSM-Layer. Fix upstream:
`9d817213a model : load hparams.n_layer_nextn before n_layer() calls (#28159)`
-- enthalten ab Tag `b10741`.

Der neue Build liegt in `llama.cpp-b10741/` (git worktree, der alte Build ist
unangetastet). Konfiguriert wurde er mit (ROCm 7.11, gfx1031):

```bash
export ROCM_PATH=/opt/rocm HIP_PLATFORM=amd HIP_PATH=/opt/rocm
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_HIP_COMPILER=/opt/rocm/lib/llvm/bin/clang++ -DCMAKE_HIP_PLATFORM=amd \
  -DCMAKE_HIP_FLAGS="--rocm-device-lib-path=/opt/rocm/lib/llvm/amdgcn/bitcode" \
  -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1031 -DGPU_TARGETS=gfx1031 \
  -DGGML_HIP_NO_VMM=ON -DGGML_HIP_MMQ_MFMA=ON -DGGML_NATIVE=ON \
  -DBUILD_SHARED_LIBS=ON -DLLAMA_CURL=ON
```

(Ohne `HIP_PLATFORM`/`--rocm-device-lib-path` bricht cmake mit
`cannot find ROCm device library` bzw. `Unexpected HIP_PLATFORM` ab.)

Beim Laden meldet b10741 die `blk.64`-Tensoren als `unused tensor -- ignoring`;
das ist korrekt, der MTP-Head wird nicht gebraucht.

**VRAM-Warnung:** Das 27B belegt 11,49 von 11,98 GiB -- 96 %. `parallel > 1`
oder `ctx-size > 8192` kippt in OOM, und eine VRAM-Spitze des Desktops kann den
Server mitreissen. Fuer Dauerbetrieb ist das Modell auf dieser Karte zu gross.

## host/port aus der ini werden ignoriert (ab b10741)

Im Router-Modus (`--models-preset`) uebernimmt b10741 `host` und `port` **nicht**
aus der ini -- der Server bindet auf `127.0.0.1:8080`, Home Assistant kaeme von
aussen nicht mehr dran. `run_profile.sh` uebergibt beide deshalb explizit per
CLI (`--host`/`--port`, ueberschreibbar via `HOST=`/`PORT=`). In
`profiles/default.ini` stehen die Zeilen nur noch auskommentiert als
Dokumentation.

## Dieses Repo ist das Produktiv-LLM von Home Assistant

`start_llama_server.sh` ist der `ExecStart` der systemd-User-Unit
`llama-server.service`. Die Unit ist `enabled`, und `systemctl --user start
llama-server.service` ist der normale Startweg. Damit ist jede Aenderung an
diesem Skript eine **Produktivaenderung an Home Assistant** auf `thinkthing`:

- Der `llm-router` (`thinkthing:11436`) nutzt `192.168.178.51:8080` als Primary
  und faellt sonst auf OpenCode Go in der Cloud zurueck. Solange dieser Dienst
  aus ist, verlassen bei jeder Wakeword-Aeusserung die Namen und Zustaende der
  19 freigegebenen Entitaeten das LAN.
- Der Alias muss `locales_llm` bleiben, sonst findet HA das Modell nicht.
- Zwei Slots mit je 16.384 Token sind in `docs/voice-stack.md` des
  Smarthome-Repos festgeschrieben (`PARALLEL=2`, `CTX=32768`).
- `MODEL_PATH` ist per Env ueberschreibbar, damit die Unit ein Modell
  festnageln kann, ohne dass `profiles/default.ini` es mitzieht.

Das Smarthome-Repo verlangt: *"Ein groesserer Kandidat muss erst im identischen
HA-Test gewinnen, bevor er dieses Modell ersetzt."*

### gemma-4-12B im HA-Test, 01.09.2026

Gemessen ueber `conversation.process` gegen
`conversation.locales_llm_ai_agent`, drei Laeufe je Frage, erster Lauf als
Kaltstart verworfen:

| Fall | Werkzeug | warm | Ergebnis |
| --- | --- | ---: | --- |
| "Wie spaet ist es?" | `GetDateTime` | 2,07 s | "Es ist 22 Uhr 12." |
| "Wie warm ist es im Bad?" | `GetLiveContext` | 4,4 s | "Im Bad sind es aktuell 24 Grad." |
| "Mach das Licht im Bad an." | Lichtwerkzeug | 1,87-1,93 s | Werkzeug gewaehlt |
| "Mach das Licht im Gang an." | Lichtwerkzeug | 2,18 s | `light.gang_licht` off -> on |

Die dokumentierte Referenz fuer Qwen3.5-9B lautet "waehlte das Lichtwerkzeug in
rund 1,95 Sekunden korrekt" -- gemma-4-12B liegt mit 1,87-1,93 s gleichauf.
Tool-Calling funktioniert also auch mit abgeschaltetem Thinking.

**Der Bad-Test beweist nur die Werkzeugwahl, nicht die Ausfuehrung:**
`light.bad_deckenlicht` ist seit 10:02 `unavailable`, es ging kein Licht an,
obwohl die Antwort das behauptete. Den Beweis am Geraet liefert erst der
Gang-Test. Wer hier misst, prueft vorher, ob die Zielentitaet ueberhaupt
erreichbar ist.

## Profile

Die Profile in `profiles/*.ini` legen fest, welches Modell mit welchen Parametern geladen wird.

```bash
./run_profile.sh              # lädt profiles/default.ini (derzeit gemma-4-12B-it-qat)
./run_profile.sh multi-user   # identisch zu default
./run_profile.sh speed        # kurzer Kontext, schneller
./run_profile.sh stable       # größerer Kontext, stabil
./run_profile.sh longctx      # 49k Kontext (experimentell)
```
