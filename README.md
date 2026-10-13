# Kiosk

Der Büro-Bildschirm für einen Raspberry Pi, im hellen, ruhigen Design und im Vollbild, passend für
720p bis 4K, quer und hochkant. Was er zeigt und wo, stellst du in der **Verwaltung** ein, die
jedes Gerät im Firmennetz im Browser öffnen kann (Computer, Tablet, Handy).

**Kacheln:** Uhr und Datum (digital oder analog, mit Kalenderwoche und nächstem Feiertag in
Hessen), Wetter vom Deutschen Wetterdienst (amtliche Warnungen, Stunden- und 7-Tage-Vorschau),
Nachrichten aus beliebig vielen RSS-Feeds (Standard: Rheinmetall und Kassel), Firmenlogo,
Mitteilung (etwa eine Begrüßung für Besuch), Countdown, Weltzeit, Monatskalender, Bilder im
Wechsel, „Tage seit“ (etwa ohne Arbeitsunfall), **Aktie** (Kurs, Veränderung, Tageskurve) und
**Abfahrten** an einer Haltestelle (live mit Verspätungen und Ausfällen, auch KVG und NVV).

Auf dem Pi läuft nur, was Raspberry Pi OS ohnehin mitbringt: Python 3 und Chromium. Kein Node,
kein pip, keine API-Schlüssel.

## Einrichten auf dem Raspberry Pi

### Mit dem Einrichtungsfenster

1. Auf dem Pi im Browser bei GitHub anmelden, das Repository öffnen, „Code“ → „Download ZIP“, und
   die ZIP-Datei im Dateimanager entpacken (am besten nach `~/kiosk`). Oder mit Git:
   `git clone https://github.com/mauricekleindienst/kiosk.git ~/kiosk`.
2. Im Ordner doppelt auf **„Kiosk einrichten“** klicken (beim Nachfragen „Ausführen“ wählen).
3. Das Fenster prüft das System, fragt nach der Verwaltung im Netz und HDMI-CEC, richtet den
   Zugang für automatische Updates ein (Deploy Key erzeugen, auf GitHub eintragen, prüfen) und
   installiert alles. Es zeigt am Ende die Adresse der Verwaltung und bietet den Neustart an.

Danach steht „Kiosk einrichten“ auch im Startmenü unter „Einstellungen“, zum Reparieren oder
Entfernen.

### Im Terminal

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

## Nachtmodus

Unter „Einstellungen“ → „Bildschirm“: zum Beispiel 19–7 Uhr und am Wochenende aus. Standardmäßig
schaltet der Pi dann das Bildsignal ab (`wlr-randr` unter Wayland, DPMS unter X11), der Monitor
geht in Standby und spart Strom. Für Fernseher gibt es zusätzlich HDMI-CEC (Paket `v4l-utils`,
`sudo apt install v4l-utils`). Um 7 Uhr geht alles wieder an.

## Automatische Updates

Der Kiosk holt sich nachts (Standard 3:15 Uhr, einstellbar unter „Gerät“) die neueste Version aus
GitHub: nur als Fast-Forward, nie über lokale Änderungen, und mit Selbsttest. Besteht die neue
Version ihn nicht, bleibt die alte. Nach einem Update startet der Dienst neu und der Bildschirm lädt
die neuen Dateien. Unter „Gerät“ stehen das Ergebnis der letzten Prüfung und „Jetzt nach Updates
suchen“.

Dafür braucht der Pi Lesezugriff auf das Repository. Bei einem privaten Repository geht das mit
einem **Deploy Key**; der grafische Installer richtet ihn ein. Von Hand:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/kiosk_deploy -C "kiosk@$(hostname)"
cat ~/.ssh/kiosk_deploy.pub    # auf GitHub: Repository → Settings → Deploy keys → Add deploy key (nur lesen)
printf 'Host github-kiosk\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/kiosk_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
cd ~/kiosk && git remote set-url origin git@github-kiosk:mauricekleindienst/kiosk.git
```

Von Hand aktualisieren: `cd ~/kiosk && ./scripts/update.sh && systemctl --user restart kiosk`.

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
- **Aktie:** Yahoo Finance (ohne Schlüssel, etwa 15 Minuten verzögert). Die Schnittstelle ist
  inoffiziell: Sie kann sich ändern oder Anfragen ablehnen, und ihre Nutzungsbedingungen erlauben
  keine kommerzielle Nutzung. Für den dauerhaften Einsatz im Unternehmen besser einen lizenzierten
  Anbieter wählen; die Quelle ist dafür austauschbar (`server/kiosk/stock.py`).
- **Abfahrten:** `v6.db.transport.rest`, die offene Schnittstelle zum Fahrplan der Deutschen Bahn
  (enthält Tram und Bus von KVG und NVV). Kostenlos, ohne Schlüssel, ohne Garantie.
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
