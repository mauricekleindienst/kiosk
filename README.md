# Kiosk

Der Büro-Bildschirm für einen Raspberry Pi, im hellen, ruhigen Design und im Vollbild, passend für
720p bis 4K, quer und hochkant. Was er zeigt und wo, stellst du in der **Verwaltung** ein, die
jedes Gerät im Firmennetz im Browser öffnen kann (Computer, Tablet, Handy).

**Kacheln:** Uhr und Datum (digital oder analog, mit Kalenderwoche und nächstem Feiertag in
Hessen), Wetter vom Deutschen Wetterdienst (amtliche Warnungen, Stunden- und 7-Tage-Vorschau),
Nachrichten aus beliebig vielen RSS-Feeds (Standard: Rheinmetall und Kassel), Firmenlogo,
Mitteilung (etwa eine Begrüßung für Besuch), Countdown, Weltzeit, Monatskalender, Bilder im
Wechsel und „Tage seit“ (etwa ohne Arbeitsunfall).

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

## Verwaltung

Beim ersten Start zeigt der Bildschirm unten einen Hinweis mit der Adresse der Verwaltung,
etwa `http://raspberrypi.local:8081`, und einem sechsstelligen Code. Öffne die Adresse auf einem
Gerät im selben Netz, gib den Code ein und lege ein Passwort fest. Danach verschwindet der Hinweis.
Nur wer vor dem Bildschirm steht, kann die Verwaltung also einrichten.

- **Layout:** Kacheln in einem Raster von 12 × 8 Feldern verschieben (ziehen) und in der Größe
  ändern (Ecke unten rechts ziehen). Mit der Tastatur: Pfeiltasten verschieben,
  Umschalt+Pfeiltasten ändern die Größe, Entf entfernt. Rechts stellst du die gewählte Kachel ein.
  Neue Kacheln und fertige Vorlagen (Standard, Nachrichten im Fokus, Empfang, Werk und Produktion,
  Hochformat, Übersicht) stehen darunter. „Vorschau“ zeigt den Bildschirm, wie er gerade aussieht.
- **Logo und Bilder:** Firmenlogo und Bilder hochladen (PNG, JPEG, WebP, GIF, SVG, bis 8 MB). Das
  Logo erscheint als eigene Kachel (frei platzierbar und skalierbar) oder in der Uhr-Kachel.
- **Einstellungen:** Standort für das Wetter (mit Ortsliste), Zeitzone, Schriftgröße, Abstände,
  Nachtabschaltung (zum Beispiel 19–7 Uhr und am Wochenende), Uhrzeit des nächtlichen Neuladens.
- **Gerät:** ob der Bildschirm verbunden ist, Stand der Datenquellen, Daten jetzt aktualisieren,
  Bildschirm neu laden, Passwort ändern.

Jede Änderung gilt sofort, der Bildschirm übernimmt sie innerhalb von drei Sekunden. Unten
erscheint jeweils „Rückgängig“.

**Sicherheit:** Die Verwaltung ist nur im lokalen Netz erreichbar, über HTTP (ohne Verschlüsselung,
wie bei den meisten Geräten im Büronetz). Passwort mit scrypt gespeichert, Anmeldung mit Sperre
nach Fehlversuchen, Schutz gegen Anfragen von fremden Seiten, Uploads werden auf ihren Inhalt
geprüft. Der Bildschirm selbst ist nur auf dem Pi erreichbar (`127.0.0.1`).

**Passwort vergessen?** Auf dem Pi `rm ~/.config/kiosk/admin.json && systemctl --user restart
kiosk`; danach zeigt der Bildschirm einen neuen Code.

**Verwaltung abschalten:** in `~/.config/kiosk/config.json` `{"adminPort": null}` eintragen und
den Dienst neu starten.

## Aktualisieren

```bash
cd ~/kiosk && git pull && systemctl --user restart kiosk
```

Danach in der Verwaltung unter „Gerät“ auf „Bildschirm neu laden“, oder bis zum nächtlichen
Neuladen warten.

## Datei-Einstellungen (optional)

Fast alles stellst du in der Verwaltung ein; gespeichert wird es in `~/.config/kiosk/settings.json`.
Für die Technik gibt es `~/.config/kiosk/config.json`. Darin stehen nur die Werte, die von
`config.default.json` abweichen, danach `systemctl --user restart kiosk`:

| Schlüssel | Bedeutung |
|---|---|
| `port` | Port des Bildschirms (nur auf `127.0.0.1` erreichbar) |
| `adminHost`, `adminPort` | wo die Verwaltung erreichbar ist; `adminPort: null` schaltet sie ab |
| `weather.refreshMinutes`, `news.refreshMinutes` | wie oft neu geladen wird |
| `news.maxAgeDays` | ältere Meldungen werden nicht gezeigt |
| `location`, `news.main`, `news.side`, `display.reloadAt` | nur für das allererste Layout, bevor in der Verwaltung etwas gespeichert wurde |

Ist die Datei fehlerhaft, startet der Dienst nicht und sagt im Log, welcher Wert falsch ist:
`journalctl --user -u kiosk`.

## Datenquellen

- **Wetter und Warnungen:** Deutscher Wetterdienst (Open Data, MOSMIX und Messstationen) über
  die freie [Bright Sky API](https://brightsky.dev). Kein Schlüssel nötig, kommerzielle Nutzung
  erlaubt, Quellenangabe steht auf dem Bildschirm.
- **Nachrichten:** RSS-Feeds der Google-News-Suche (Standard: „Rheinmetall“ und „Kassel“). Jeder
  andere RSS- oder Atom-Feed geht ebenfalls; die Adresse trägst du in der Nachrichten-Kachel ein.
- **Feiertage, Sonnenauf- und -untergang:** werden lokal berechnet.

Fällt eine Quelle aus, bleibt der letzte Stand stehen und die Kachel zeigt dezent
„Keine Verbindung – Stand 09:41 Uhr“. Der letzte Stand übersteht auch einen Neustart ohne Netz.

## Entwicklung

```bash
npm ci                       # nur für die Tests (Playwright)
npm run test:server          # Python: Server, Einstellungen, Anmeldung, Uploads, Schnittstellen
npm run test:scripts         # Installations- und Startskripte mit Platzhaltern
npm run test:unit            # Formatierung, Feiertage, Raster, Design-Regeln, Kontrast, Texte
npm run test:e2e             # Bildschirm und Verwaltung in Chromium, 6 Bildschirmgrößen
shellcheck scripts/*.sh
```

Lokal ansehen mit Beispieldaten (ohne Internet): `node tests/e2e/serve.mjs`, dann Bildschirm
http://127.0.0.1:8199 und Verwaltung http://127.0.0.1:8198. Mit echten Daten:
`cd server && python3 -m kiosk`, dann http://127.0.0.1:8080 und http://127.0.0.1:8081.

Aufbau und Entscheidungen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Schrift: [Inter](https://rsms.me/inter/) (SIL Open Font License, `web/shared/fonts/OFL.txt`).
