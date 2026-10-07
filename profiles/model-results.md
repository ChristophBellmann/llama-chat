# Gemessene Modellprofile, 07.10.2026

RX 6700 XT: 11,98 GiB VRAM; Ryzen 9 3900X: 31,25 GiB RAM. Orpheus und Desktop sind in der Gesamtbelegung enthalten.

| Modell | Kontext | Batch/Micro | Tokens/s | VRAM gesamt GiB | Reserve GiB | Prozess-RSS GiB | Orpheus RTF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dirk-Qwen3.8-27B-UD-IQ3_XXS † | 8,192 | 512/256 | 3.3 | 10.77 | 1.22 | 4.85 | 0.94 |
| Loxa-3B-F16 | 16,384 | 512/256 | 47.2 | 10.62 | 1.37 | 1.14 | 1.00 |
| Loxa-3B-Q4_K_M | 65,536 | 1024/512 | 97.1 | 9.51 | 2.48 | 0.73 | 1.01 |
| Qwen3-14B-Q4_K_M † | 8,192 | 512/256 | 11.4 | 10.76 | 1.22 | 2.42 | 0.96 |
| Qwen3.5-9B-Q4_K_M | 65,536 | 1024/512 | 48.8 | 9.84 | 2.15 | 1.21 | 1.01 |
| Qwen3.6-35B-A3B-UD-IQ2_M † | 8,192 | 512/256 | 44.0 | 10.65 | 1.33 | 11.21 | 0.95 |
| Qwen3.8-27B-UD-IQ2_S † | 8,192 | 512/256 | 2.3 | 10.87 | 1.12 | 2.69 | 0.98 |
| Qwen3.8-27B-UD-IQ2_XXS | 8,192 | 512/256 | 21.6 | 10.82 | 1.16 | 1.45 | 0.96 |
| Qwen_Qwen3.6-27B-Q4_K_M † | 8,192 | 512/256 | 2.7 | 10.50 | 1.49 | 11.13 | 0.94 |
| gemma-4-12B-it-qat-UD-Q4_K_XL | 16,384 | 512/256 | 37.2 | 10.26 | 1.72 | 1.30 | 0.94 |
| gemma-4-E4B-it-ultra-uncensored-heretic-Q8_0 | 131,072 | 512/256 | 47.0 | 10.00 | 1.98 | 4.03 | 0.96 |
| qwen35-4b-same-gguf-fast-Q4_K_M | 65,536 | 512/256 | 74.2 | 7.65 | 4.34 | 0.90 | 0.99 |

† Teile des Modells rechnen auf CPU. Beim MoE-Modell koennen CPU-Experten aktiv sein, obwohl die Anzahl GPU-Schichten alle Bloecke umfasst.

Kontextlimits wurden mit reserviertem Cache und kurzen bzw. etwa 1.500–2.000 Tokens langen Anfragen geprueft. Das ist kein Geschwindigkeitstest mit voll gefuelltem Kontext und keine umfassende Qualitaetsbewertung.

Tokens/s ist die gemessene Generierung des Antworttexts. RAM-RSS schliesst gemappte Dateiseiten ein und ist nicht gleich dem dauerhaft notwendigen CPU-Arbeitsspeicher. Alle gewaehlten Profile meldeten 0 MiB Prozess-Swap und 0 MiB evicted VRAM.

RTF um 1 bedeutet nahezu Echtzeit. Die Modellprofile stammen aus zwei Messreihen; sieben Profile wurden mit strengerer Reserve und deaktivierten Orpheus-GPU-Graphs erneut gemessen. Der erste Audioton lag in diesen Wiederholungen bei etwa 0,6 Sekunden.

Die volle GPU-Konfiguration von IQ2_S erreichte zuvor etwa 20,5 Tokens/s, hatte aber nur wenige hundert MiB Reserve. Das hier gewaehlte Profil priorisiert Reserve neben Orpheus und ist wegen CPU-Schichten deutlich langsamer. XXS ist die bessere 27B-Option fuer schnellen Betrieb auf dieser GPU.

Qwen3.5 wurde auch mit 131.072 Kontext-Tokens geladen und getestet. Dabei musste die automatische Anpassung Teile auf CPU legen; das voll auf GPU laufende 65.536-Profil wurde deshalb bevorzugt.

Details: [Profilbeschreibung](README.md), [Einstellungen](model-settings.json), [Rohmessungen](model-measurements.json).
