# WLAN-Aufwecken und Standby

Produktiv eingerichtet und zweimal praktisch getestet am 06.10.2026.
Workstation-Profil `Ultranet` ist dauerhaft auf
`802-11-wireless.wake-on-wlan magic` gesetzt. Die Intel AX200 meldet
Magic-Packet-Unterstützung. Suspend-Modus ist `deep`.

`workstation-power.service` läuft als Benutzer `christoph`, Port 8091.
Nur `192.168.178.55` mit passendem Bearer-Schlüssel darf `/status` lesen und
`/suspend` bzw. `/suspend-idle` aufrufen. Schlüssel liegt ausschließlich in
`~/.config/workstation-power/config.json`, Modus 600. Niemals ins Git übernehmen.

## Administrator-Schritt bei Neuinstallation

Im eigenen Terminal auf der Workstation:

```bash
bash /media/christoph/some_space/Compute/ML-Lab/llama-chat/power/enable_standby.sh
```

Aktiviert WoWLAN für die aktuelle Verbindung und erlaubt über eine mit
`visudo` geprüfte sudoers-Datei genau `systemctl --no-block suspend`.
Versetzt den Rechner noch nicht in Standby. Auf dieser Workstation waren
keine BIOS-Änderungen nötig; WoWLAN aus Suspend wurde zweimal nachgewiesen.

## Home Assistant vorbereiten und installieren

Live-Klon: `/home/christoph/home-assistant` auf `thinkthing`.
Die HA-Änderungen sind installiert. Für Neuinstallation den SSH-Schlüssel
bei Bedarf im eigenen Terminal entsperren:

```bash
ssh-add ~/.ssh/id_rsa
```

Nach Prüfung des aktuellen Live-Stands `power/` auf den Server übertragen.
`python3 power/stage_ha.py /home/christoph/home-assistant` bereitet Router,
Compose, HA-Paket und die Workstation-Karte im Dashboard Sprachassistent vor.
Das Werkzeug startet keine Dienste und bricht bei unerwarteten Quellstellen ab.
Es gehört nicht zum regulären Betrieb; die resultierenden Dateien werden im
HA-Repository versioniert.

Den lokalen Schlüssel geschützt in die vorhandene, nicht versionierte `.env`
des HA-Klons als `WORKSTATION_POWER_TOKEN` übernehmen (nicht ausgeben).
Dann Router-Tests, `docker compose config --quiet` und HA-`check_config`
ausführen. Router neu bauen/starten; erst nach gültiger Konfiguration HA
neu starten. Automatische Standby-Steuerung erst nach einem erfolgreichen
Schlaf-/Aufwecktest einschalten. Der Schalter im Dashboard Sprachassistent
bleibt über HA-Neustarts erhalten.

Der vorhandene Router bekommt vor `POST /v1/chat/completions` einen
Aufweckschritt. Er prüft `/health`, sendet bei Bedarf wiederholt ein Magic
Packet an die WLAN-MAC `c8:b2:9b:df:73:20`, Broadcast `192.168.178.255:9`,
und wartet maximal etwa 45 Sekunden. Anschließend wird dieselbe Anfrage mit
dem ursprünglichen Body an den bestehenden Router weitergegeben; bei
fehlgeschlagenem Aufwecken greift dessen vorhandener Fallback. Healthchecks,
Modelllisten und explizite Fallback-Tests wecken nicht auf.

## Standby und Test

Vor dem ersten Standby muss vom HA-Server aus ein authentifizierter Zugriff
auf Port 8091 erfolgreich sein. Eventuelle Firewall-Regeln nur für
`192.168.178.55` öffnen. HA-Host und Workstation brauchen feste DHCP-Zuordnungen.

Beim kontrollierten Test Standby ankündigen, dann von `thinkthing` wiederholt
Weckpakete senden. Danach `/health` auf 8080 und lokal 8082 prüfen sowie
LLM-Inferenz und Orpheus testen. Ein BIOS- oder GPU-Resume-Problem ist erst
dann ausgeschlossen, wenn diese echten Anfragen funktionieren.

Der manuelle Standby-Button blockiert während Modell-/GPU-/hoher CPU-Arbeit
und bei laufender lokaler Audioausgabe
und kurz nach einer LLM-Anfrage. Der optionale automatische Standby wartet
zusätzlich mindestens 30 Minuten seit der letzten LLM-Anfrage und seit der
letzten Desktop-Eingabe. Unbekannte Slot-, GPU- oder Desktop-Aktivität
blockiert den entsprechenden Standby-Versuch. CPU-Last und GPU-Auslastung
sind Indikatoren und erkennen nicht jede beliebige Hintergrundarbeit.

Orpheus wird durch dieselbe LLM-Anfrage mit aufgeweckt. Ein eigenständiger
TTS-Aufruf direkt an die schlafende Wyoming-Schnittstelle hat noch keinen
Aufweck-Proxy. Ohne LLM-Anfrage vorher muss der Aufweck-Button benutzt werden.

Erster Test: tatsächlicher Suspend/Resume; eine LLM-Anfrage weckte den Rechner
und lieferte nach 16,79 Sekunden die Testantwort. Zweiter Test über HA-Buttons:
Aufweckskript nach 11,36 Sekunden erfolgreich. Orpheus lieferte nach Resume
129.792 Audio-Bytes und AudioStop. 7 lokale Schutzprüfungen und 19 HA-Routertests
erfolgreich. Betriebsdokumentation auf thinkthing:
`/home/christoph/home-assistant/docs/workstation-wowl-2026-10-06.md`.

## Rückbau

```bash
systemctl --user disable --now workstation-power.service
nmcli connection modify Ultranet 802-11-wireless.wake-on-wlan default
sudo iw phy phy0 wowlan disable
sudo rm /etc/sudoers.d/workstation-power
```

HA-Paket und Dashboard-Karte entfernen, Router-Hooks zurücknehmen und erst
nach Konfigurationsprüfung neu starten. Den bisherigen LLM-Fallback erhalten.

## Modellauswahl in Home Assistant

Das Dashboard **Sprachassistent → Workstation** enthält das Dropdown
`select.workstation_modell`, das geladene Modell und den Wechselstatus.
Die Liste kommt aus den tatsächlich vorhandenen `models/*.gguf` im
Llama-Chat-Arbeitsverzeichnis. Symlinks werden dedupliziert; Modelle außerhalb
von `models/` und die separaten Sprachmodelle in Unterordnern werden nicht
angeboten. Neue Dateien erscheinen beim nächsten Statusabruf (zehn Sekunden).

Die Auswahl weckt bei Bedarf über den bestehenden Router auf und startet
nur `llama-server.service` neu. Alle Clients auf Port 8080 verwenden damit
das ausgewählte Modell. Der Alias `locales_llm` bleibt bestehen. Die Auswahl
ändert keinen HA-Sprach-Agenten; für die Workstation muss dort weiterhin
`Local LLM Router` oder `Workstation (llama.cpp)` gewählt sein.

`power/model_control.py` schreibt die dauerhafte Auswahl nach
`~/.config/systemd/user/llama-server.service.d/zz-ha-model.conf`. Die bisherigen
Drop-ins bleiben erhalten. Verwendet werden ein Slot, 8.192 Token Kontext und
512/256 Batch-Größe. Dateien über 12 GiB erhalten 20 GPU-Layer, damit ein Teil
auf der CPU bleibt; das kann deutlich langsamer sein. Diese vorsichtigen Werte
sind keine Qualitäts- oder Geschwindigkeitsbewertung jedes angebotenen Modells.
Ein Ladefehler stellt den vorherigen Inhalt des neuen Drop-ins wieder her
(beim ersten Wechsel wird es entfernt) und startet das vorherige Modell.
Health und tatsächlicher Modellpfad müssen innerhalb von 150 Sekunden stimmen;
ein weiterer Wechsel und Standby sind währenddessen gesperrt. Laufende
Router-Anfragen sowie aktive Llama-/Orpheus-Slots blockieren den Wechsel.

Die authentifizierte Workstation-Schnittstelle erhält `GET /models` und
`POST /models` mit `{"model": "Dateiname.gguf"}`. Für Home Assistant stellt
nur der Loopback-Router `GET/POST /workstation/models` bereit; der bestehende
Schlüssel und die Host-Beschränkung bleiben maßgeblich. Statusabrufe wecken
nicht auf. Solange die Workstation schläft, behält der Router seine zuletzt
abgerufene Liste im Speicher und meldet ausdrücklich „nicht erreichbar“.
Nach einem Router-Neustart steht die Liste erst beim nächsten erreichbaren
Workstation-Abruf zur Verfügung. „Geladenes Modell“ kann während des Schlafs
den letzten bestätigten Stand zeigen; entscheidend ist zusätzlich der Status.

`power/workstation_models_ha.yaml` ist die Vorlage für
`/home/christoph/home-assistant/config/packages/workstation_models.yaml` auf
thinkthing. `power/stage_ha.py` übernimmt die Vorlage und Dashboard-Zeilen.
Lokale Prüfungen: `python3 -m unittest power.test_power power.test_models -q`.
Die Routertests aus `power/ha_test_router.py` laufen im HA-Klon unter
`llm-router/tests/test_workstation_power.py`.

Zum Rückbau Dropdown, Modell-Paket und Router-Erweiterung entfernen; den
Drop-in `zz-ha-model.conf` löschen und danach `systemctl --user daemon-reload`
sowie einen kontrollierten Llama-Neustart ausführen. Das aktiviert wieder die
vorherige Modellkonfiguration. HA vor einem Neustart mit `check_config` prüfen.
