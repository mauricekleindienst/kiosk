# Kiosk

Der Büro-Bildschirm für einen Raspberry Pi: große Uhr mit Datum, Kalenderwoche und nächstem
Feiertag in Hessen, Wetter für Kassel vom Deutschen Wetterdienst (mit amtlichen Warnungen,
12-Stunden- und 7-Tage-Vorschau) und die aktuellen Nachrichten zu Rheinmetall sowie zu Kassel und
der Region. Helles, ruhiges Design im Vollbild, passend für 720p bis 4K, quer und hochkant.

Auf dem Pi läuft nur, was Raspberry Pi OS ohnehin mitbringt: Python 3 und Chromium. Kein Node,
kein pip, keine API-Schlüssel.

## Einrichten auf dem Raspberry Pi

Voraussetzung: Raspberry Pi OS **Bookworm oder neuer** mit Desktop, automatische Anmeldung des
Desktop-Benutzers (Standard bei der Einrichtung; sonst `sudo raspi-config` → System Options →
Boot / Auto Login → Desktop Autologin) und Netzwerk.

```bash
git clone https://github.com/mauricekleindienst/kiosk.git ~/kiosk
cd ~/kiosk
./scripts/install.sh
sudo reboot
```

Nach dem Neustart öffnet sich der Bildschirm von selbst im Vollbild. Das Skript

- richtet den Datenserver als Benutzer-Dienst ein (`kiosk.service`, startet beim Booten und nach
  einem Absturz neu),
- startet Chromium im Kiosk-Modus bei jeder Anmeldung (XDG-Autostart, labwc und wayfire) und
  öffnet ihn neu, falls er beendet wird oder abstürzt,
- schaltet die Bildschirmabschaltung aus,
- installiert Chromium nach, falls er fehlt.

Erneut ausführen ist unbedenklich. Zum Entfernen: `./scripts/uninstall.sh`.

Chromium schließen (`Alt+F4`) öffnet ihn nach 5 Sekunden wieder; das ist Absicht. Für Wartung am
Desktop: `./scripts/uninstall.sh` und neu starten, danach `./scripts/install.sh` wieder ausführen.

### Aktualisieren

```bash
cd ~/kiosk && git pull && systemctl --user restart kiosk
```

Die Seite lädt sich jede Nacht um 3:30 Uhr selbst neu und übernimmt dabei neue Oberflächen-Dateien.

## Einstellungen

Alles funktioniert ohne Einstellungen. Wer etwas ändern will, legt `~/.config/kiosk/config.json`
an. Darin stehen nur die Werte, die von `config.default.json` abweichen, zum Beispiel:

```json
{
  "location": { "name": "Unterlüß", "lat": 52.8333, "lon": 10.2833 },
  "news": {
    "main": { "title": "Rheinmetall", "limit": 6 },
    "side": {
      "title": "Hessen",
      "url": "https://news.google.com/rss/search?q=Hessen&hl=de&gl=DE&ceid=DE:de"
    }
  }
}
```

Danach `systemctl --user restart kiosk`. Ist die Datei fehlerhaft, startet der Dienst nicht und
sagt im Log, welcher Wert falsch ist: `journalctl --user -u kiosk`.

| Schlüssel | Bedeutung |
|---|---|
| `location` | Ort für das Wetter (Name, Breite, Länge) |
| `news.main`, `news.side` | Titel, Feed-Adresse (RSS oder Atom) und Höchstzahl der Meldungen für den großen und den kleinen Nachrichtenblock |
| `news.maxAgeDays` | ältere Meldungen werden nicht gezeigt |
| `weather.refreshMinutes`, `news.refreshMinutes` | wie oft neu geladen wird |
| `display.reloadAt` | Uhrzeit des nächtlichen Neuladens |
| `port` | lokaler Port des Datenservers (nur auf `127.0.0.1` erreichbar) |

Es werden nur so viele Meldungen gezeigt, wie vollständig auf den Bildschirm passen.

## Datenquellen

- **Wetter und Warnungen:** Deutscher Wetterdienst (Open Data, MOSMIX und Messstationen) über
  die freie [Bright Sky API](https://brightsky.dev). Kein Schlüssel nötig, kommerzielle Nutzung
  erlaubt, Quellenangabe steht auf dem Bildschirm.
- **Nachrichten:** RSS-Feeds der Google-News-Suche (Standard: „Rheinmetall“ und „Kassel“).
  Jeder andere RSS- oder Atom-Feed geht ebenfalls.
- **Feiertage, Sonnenauf- und -untergang:** werden lokal berechnet.

Fällt eine Quelle aus, bleibt der letzte Stand stehen und der Block zeigt dezent
„Keine Verbindung – Stand 09:41 Uhr“. Der letzte Stand übersteht auch einen Neustart ohne Netz.

## Entwicklung

```bash
npm ci                       # nur für die Tests (Playwright)
npm run test:server          # Python: Server, Feeds, Wetter, Konfiguration
npm run test:scripts         # Installations- und Startskripte mit Platzhaltern
npm run test:unit            # Formatierung, Feiertage, Design-Regeln, Kontrast
npm run test:e2e             # echte Seite in Chromium, 6 Bildschirmgrößen
shellcheck scripts/*.sh
```

Lokal ansehen mit Beispieldaten (ohne Internet): `node tests/e2e/serve.mjs`, dann
http://127.0.0.1:8199 öffnen. Mit echten Daten: `cd server && python3 -m kiosk`, dann
http://127.0.0.1:8080.

Aufbau und Entscheidungen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Schrift: [Inter](https://rsms.me/inter/) (SIL Open Font License, `web/fonts/OFL.txt`).
