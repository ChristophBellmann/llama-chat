# Modellprofile mit Orpheus

`model-settings.json` enthaelt die gemessenen Einstellungen fuer die
Modellauswahl in Home Assistant. `power/model_control.py` liest fuer jeden
Wechsel die Defaults und das Profil des gewaehlten Dateinamens. Qwen3.5-9B
bleibt damit ebenso waehlbar wie Qwen3.8; jeder Wechsel setzt auch Kontext,
Batch, Microbatch und GPU-Speicherbudget passend zum Modell.

Gemessen auf RX 6700 XT mit 11,98 GiB VRAM und Ryzen 9 3900X mit 31,25 GiB
RAM, llama.cpp b10741. Orpheus, Wyoming und der Desktop bleiben aktiv.
Die gemessenen Profile verwenden einen Slot, q8_0 fuer beide KV-Caches und
deaktivierte HIP-Graphs. Auch Orpheus verwendet GPU-Offloading und deaktivierte
HIP-Graphs. Ein langer Audiostart wurde in der ersten Messreihe beobachtet;
die Wiederholungsmessungen nach dieser Anpassung sind im Report enthalten.

Die Speicherprognose von HIP ist nicht gleich dem tatsaechlich belegten VRAM.
Deshalb wird der `LLAMA_ARG_FIT_TARGET` fuer knappe Modelle anhand der realen
Gesamtbelegung nachkalibriert. Ziel ist etwa 1 GiB Reserve fuer Desktop und
Laufzeitpuffer. `GPU_LAYERS=auto` passt die Auslagerung beim naechsten Laden
erneut an die dann freie GPU an. Grosse Modelle bleiben waehlbar, koennen aber
CPU-Schichten oder CPU-Experten benoetigen und deutlich langsamer antworten.
Orpheus wird dabei nicht auf CPU verschoben.

Die Rohmessungen stehen in `model-measurements.json`; `model-results.md`
zeigt eine kompakte Tabelle. Pro getesteter Konfiguration werden eine kurze
Frage, eine Aufwaerm- und eine Messanfrage mit ungefaehr 1.500 bis 2.000
Prompt-Tokens und hoechstens 64 Antwort-Tokens ausgefuehrt. Die Profile pruefen
die Speicherreservierung des angegebenen Kontextlimits, nicht die Antwortqualitaet
oder Geschwindigkeit bei einem tatsaechlich bis zum Limit gefuellten Kontext.
RTF = Erzeugungszeit / Audiolaenge; RTF um 1 bedeutet ungefaehr Echtzeit.

`rss_mib` ist der residente Prozessspeicher inklusive gemappter Modelldatei
und wiederverwendbarer Dateiseiten. Er ist nicht gleich dem dauerhaft fuer
CPU-Rechnen erforderlichen RAM. `process_swap_mib` und `evicted_vram_mib`
werden separat geprueft. Auch vollstaendig auf GPU geladene Schichten koennen
normale Token-Embeddings oder andere modelltypische Tabellen im RAM behalten;
MoE-Tensor-Overrides werden ausdruecklich als CPU-Auslagerung markiert.

Eine erneute Kalibrierung startet man auf der Workstation mit:

```bash
voice/.venv/bin/python3 scripts/tune_model_profiles.py
# Einzelnes Modell mit groesserem zu pruefendem Kontextlimit:
voice/.venv/bin/python3 scripts/tune_model_profiles.py \
  --models Qwen3.5-9B-Q4_K_M.gguf --max-context 131072
```

Dabei werden Modelle seriell neu geladen. Die Workstation-Steuerung wird
voruebergehend pausiert, damit HA-Modellwechsel und Standby nicht dazwischenkommen.
Orpheus bleibt verfuegbar. Der Runner entfernt abschliessend seinen temporaeren
`zzz-tuning.conf`-Override und stellt das vorher geladene Modell wieder her.
GGUF-Dateien bleiben lokal; neue Modelle erhalten zunaechst die konservativen
Defaults und werden erst nach einer Messung mit einem eigenen Profil versehen.
