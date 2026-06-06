# Music Assistant + Snapcast Runbook (thinkthing)

## Ziel
- Spotify vom Handy per Spotify Connect auf den MA-Server senden.
- Ausgabe über MA-Player (z. B. SAT1 / Echo Base) und später Multiroom.
- Trennung bleibt: Assist/TTS separat von Musik.

## Deployte Komponente
- Docker-Service: `music-assistant-server`
- Image: `ghcr.io/music-assistant/server:2.8.7`
- Netzwerk: `host`
- Persistenz: `/home/christoph/home-assistant/music-assistant/data`
- Web-UI: `http://thinkthing:8095`

## Reproduzierbarer Deploy
1. Backup:
   - `cp docker-compose.yml bak/<timestamp>/docker-compose.yml`
2. Compose-Datei aktualisieren.
3. Start:
   - `docker compose up -d music-assistant-server`
4. Verifikation:
   - `docker ps | grep music-assistant-server`
   - `curl -I http://127.0.0.1:8095`
   - `docker logs --tail 200 music-assistant-server`

## Rollback
1. `docker compose stop music-assistant-server`
2. Alte Compose zurückkopieren.
3. `docker compose up -d`

## Kompatibilitätshinweis
- Bei HA-Core `2025.10.3` führte MA `2.8.8` zu:
  - `InvalidServerVersion: Schema version is incompatible: 29 ... requires at least 28`
- Daher ist MA aktuell auf `2.8.7` gepinnt.
- Nach einem HA-Core-Update kann MA wieder auf neuere Versionen angehoben werden.

## MA-Erstkonfiguration (UI)
1. MA öffnen: `http://thinkthing:8095`
2. Provider hinzufügen:
   - Home Assistant Plugin Provider (verbindet MA <-> HA)
   - Home Assistant Players Provider (damit SAT1/Echo als MA-Player verfügbar sind)
   - Spotify Music Provider (für Bibliothek/Playback in MA)
3. Für Spotify-Connect vom Handy:
   - Plugin `Spotify Connect` installieren.
   - Pro Ziel-Player einmal aktivieren.

## Snapcast (MA-intern)
- Snapcast Player Provider in MA aktivieren.
- Für echte Sync-Clients:
  - Snapclient auf Endgeräten oder Snapweb/Snapdroid verwenden.
- Hinweis:
  - HA-Player sind für Spotify-Connect als Ziel weniger robust als native MA/Snapcast-Player.
