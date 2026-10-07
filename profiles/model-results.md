# Gemessene Modellprofile, 07.10.2026

RX 6700 XT: 11,98 GiB VRAM; Ryzen 9 3900X: 31,25 GiB RAM. Desktop und bei allen Profilen außer IQ2_S Orpheus sind in der Gesamtbelegung enthalten. IQ2_S nutzt Ramona auf der CPU von thinkthing.

| Modell | Kontext | Batch/Micro | Tokens/s | VRAM gesamt GiB | Reserve GiB | Prozess-RSS GiB | TTS RTF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dirk-Qwen3.8-27B-UD-IQ3_XXS † | 8,192 | 512/256 | 3.3 | 10.77 | 1.22 | 4.85 | 0.94 |
| Loxa-3B-F16 | 16,384 | 512/256 | 47.2 | 10.62 | 1.37 | 1.14 | 1.00 |
| Loxa-3B-Q4_K_M | 65,536 | 1024/512 | 97.1 | 9.51 | 2.48 | 0.73 | 1.01 |
| Qwen3-14B-Q4_K_M † | 8,192 | 512/256 | 11.4 | 10.76 | 1.22 | 2.42 | 0.96 |
| Qwen3.5-9B-Q4_K_M | 65,536 | 1024/512 | 48.8 | 9.84 | 2.15 | 1.21 | 1.01 |
| Qwen3.6-35B-A3B-UD-IQ2_M † | 8,192 | 512/256 | 44.0 | 10.65 | 1.33 | 11.21 | 0.95 |
| Qwen3.8-27B-UD-IQ2_S (Ramona) | 65,536 | 512/256 | 20.1 | 10.87 | 1.10 | 1.48 | 0.02 |
| Qwen3.8-27B-UD-IQ2_XXS | 8,192 | 512/256 | 21.6 | 10.82 | 1.16 | 1.45 | 0.96 |
| Qwen_Qwen3.6-27B-Q4_K_M † | 8,192 | 512/256 | 2.7 | 10.50 | 1.49 | 11.13 | 0.94 |
| gemma-4-12B-it-qat-UD-Q4_K_XL | 16,384 | 512/256 | 37.2 | 10.26 | 1.72 | 1.30 | 0.94 |
| gemma-4-E4B-it-ultra-uncensored-heretic-Q8_0 | 131,072 | 512/256 | 47.0 | 10.00 | 1.98 | 4.03 | 0.96 |
| qwen35-4b-same-gguf-fast-Q4_K_M | 65,536 | 512/256 | 74.2 | 7.65 | 4.34 | 0.90 | 0.99 |

† Teile des Modells rechnen auf CPU. Beim MoE-Modell koennen CPU-Experten aktiv sein, obwohl die Anzahl GPU-Schichten alle Bloecke umfasst.

Kontextlimits wurden mit reserviertem Cache und kurzen bzw. etwa 1.500–2.000 Tokens langen Anfragen geprueft. Das ist kein Geschwindigkeitstest mit voll gefuelltem Kontext und keine umfassende Qualitaetsbewertung.

Tokens/s ist die gemessene Generierung des Antworttexts. RAM-RSS schliesst gemappte Dateiseiten ein und ist nicht gleich dem dauerhaft notwendigen CPU-Arbeitsspeicher. Alle gewaehlten Profile meldeten 0 MiB Prozess-Swap und 0 MiB evicted VRAM.

RTF um 1 bedeutet nahezu Echtzeit. Die Modellprofile stammen aus zwei Messreihen; sieben Profile wurden mit strengerer Reserve und deaktivierten Orpheus-GPU-Graphs erneut gemessen. Der erste Audioton lag in diesen Wiederholungen bei etwa 0,6 Sekunden.

IQ2_S wurde anschließend ohne Orpheus und mit Ramona neu kalibriert: alle 65 Schichten auf GPU, Kontext 65.536, FIT_TARGET 1024, 20,1 Tokens/s. Höchste Gesamtbelegung 11.140,5 MiB bei 12.272 MiB Kapazität, etwa 1,1 GiB Reserve. 131.072 Kontext mit FIT_TARGET 2048 legte 22 Schichten auf CPU und erreichte nur 1,35 Tokens/s.

Ramona lief auf thinkthing (Piper, de_DE-ramona-low). Drei Messungen erzeugten 3,09–3,47 Sekunden Audio in 1,04 / 0,085 / 0,075 Sekunden. Warmer erster Ton nach 0,026–0,032 Sekunden, RTF 0,022–0,028. Das bisherige IQ2_S-Profil **mit** Orpheus bleibt als historische Messung erhalten; aktuelle ModelControl- und Benchmark-Aufrufe verwenden das Ramona-Profil.

Qwen3.5 wurde auch mit 131.072 Kontext-Tokens geladen und getestet. Dabei musste die automatische Anpassung Teile auf CPU legen; das voll auf GPU laufende 65.536-Profil wurde deshalb bevorzugt.

Details: [Profilbeschreibung](README.md), [Einstellungen](model-settings.json), [Rohmessungen](model-measurements.json).
