# Workstation über WLAN aufwecken und in Standby versetzen

Am 06.10.2026 produktiv eingerichtet und zweimal mit echtem Suspend getestet.

## Bedienung

Im Dashboard **Sprachassistent** steht die Karte **Workstation**:

- **Aufwecken** wartet, bis das LLM bereit ist.
- **Standby** wird bei laufender Modell-, GPU-, stärkerer CPU- oder lokaler
  Audioaktivität abgelehnt.
- **Workstation nach 30 Minuten schlafen lassen** schaltet den automatischen
  Leerlaufmodus ein oder aus; der Zustand bleibt über HA-Neustarts erhalten.

Der Leerlaufmodus prüft alle fünf Minuten. Standby setzt mindestens
30 Minuten seit der letzten LLM-Anfrage und seit der letzten Desktop-Eingabe
voraus. Laufende Anfragen blockieren Standby. Unbekannte Modell-/GPU- oder
Audioaktivität blockiert ebenfalls; automatische Versuche werden bei
unbekannter Desktop-Aktivität abgelehnt. Diese Indikatoren erkennen nicht
jede beliebige Hintergrundaufgabe. Für längere unbeaufsichtigte Arbeit den
Leerlaufmodus abschalten.

## Ablauf

`llm-router/router.py` umschließt echte Chat-Anfragen mit
`WorkstationPower.request()` aus `llm-router/ha_router_power.py`.
Bei nicht erreichbarem `/health` sendet der Router wiederholt Magic Packets
an die WLAN-MAC `c8:b2:9b:df:73:20` über `192.168.178.255:9` und wartet etwa
45 Sekunden. Die ursprüngliche Chat-Anfrage wird danach unverändert
weitergereicht. Bleibt die Workstation aus, greift der vorhandene Fallback.
Modelllisten, Healthchecks und ausdrücklich erzwungene Fallback-Anfragen
wecken die Workstation nicht auf.

Die HA-Konfiguration liegt in `config/packages/workstation_power.yaml`,
die Karte in `config/lovelace/sprachassistent.yaml`. Die Steuerendpunkte sind
nur am lokalen Router und ausschließlich über dessen Loopback-Verbindung
aufrufbar. Keine externe Proxy-Route dafür anlegen.

Auf der Workstation läuft `systemctl --user status workstation-power.service`
aus dem Repository `llama-chat/power/`. Die Schnittstelle auf Port 8091
akzeptiert nur `192.168.178.55` mit passendem geheimem Schlüssel. Der Schlüssel
liegt auf der Workstation in `~/.config/workstation-power/config.json` (600),
auf thinkthing als `WORKSTATION_POWER_TOKEN` in `.env` (600). Compose gibt ihn
als `LLM_ROUTER_POWER_TOKEN` an den Router. Keine Schlüssel ausgeben oder
versionieren. Die DHCP-Zuordnungen für `.51` und `.55` müssen stabil bleiben.

Das WLAN-Profil `Ultranet` verwendet dauerhaft
`802-11-wireless.wake-on-wlan magic`. Der aktive AX200-Treiber meldet
`wake up on magic packet`. Linux verwendet `deep` (Suspend-to-RAM).
Eine geprüfte sudoers-Regel erlaubt dem Workstation-Benutzer ausschließlich
`sudo -n /usr/bin/systemctl --no-block suspend` für diese Schnittstelle.

## Verifikation

- 19 Router-Tests erfolgreich, darunter unveränderte erste Anfrage nach
  Aufwecken, erhaltener Fallback und Modellliste ohne Weckeffekt.
- HA-`check_config` und `docker compose config --quiet` erfolgreich.
- Erster echter Test: Standby um 19:25:31, Resume um 19:25:48 (Europe/Berlin).
  Während Standby war HTTP nicht erreichbar. Eine anschließende LLM-Anfrage
  weckte den Rechner und lieferte nach 16,79 Sekunden die Testantwort
  `Aufwecken erfolgreich.`. Der unabhängige Backup-Weckversuch wurde nicht
  benötigt. Diese Zahl umfasst Aufwecken und Inferenz.
- Zweiter echter Test über HA-Dienste der Dashboard-Buttons: Workstation
  zwischenzeitlich nicht erreichbar; Aufweckskript nach 11,36 Sekunden
  fertig, danach LLM-Health wieder 200. Keine Backup-Weckpakete nötig.
- Nach dem ersten Resume lieferte Orpheus über Wyoming 129.792 Audio-Bytes
  und `AudioStop`; beide Modellserver meldeten `/health` mit `status: ok`.
  Kein akustischer Test über einen Satelliten.

Es waren keine BIOS-Änderungen erforderlich. Getestet ist Standby, nicht
Aufwecken aus vollständig heruntergefahrenem Zustand. Normale Sprachantworten
wecken Orpheus mit dem vorherigen LLM-Aufruf auf. Ein eigenständiger TTS-Aufruf
direkt an die schlafende Wyoming-Schnittstelle braucht zuvor den Aufweckbutton.

Wake-Pakete selbst sind nicht auf einen Absender beschränkt; auch andere
Geräte im LAN könnten sie senden. Die eingerichtete Standby-Steuerung ist
auf den HA-Server beschränkt.
