# Haushaltsbuch

Selbst gehostetes Haushaltsbuch für **einen** Haushalt: Kassenbon fotografieren,
Positionen automatisch erfassen, sehen wo das Geld hingeht — und **was teurer
wird**.

* **Ein Container.** API und Web-Oberfläche in einem Prozess, SQLite als
  Datenbank. Kein Postgres, kein Redis, kein separater Worker.
* **Läuft ohne KI-Modell.** Digitale eBon-PDFs (REWE, Lidl, Kaufland …) liest ein
  eingebauter Parser. Ein Vision-Modell ist optional und nur für Fotos nötig.
* **Preisverläufe pro Artikel.** „H-Milch 3,5 %“ und „H MILCH 3.5“ sind derselbe
  Artikel — dafür sorgt die Namensnormalisierung.

## Schnellstart

```bash
git clone https://github.com/xcojonny/expense-diary && cd expense-diary
cp .env.example .env

# AUTH_PASSWORD und SECRET_KEY setzen:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env

docker compose up -d
```

→ <http://localhost:8000>, Anmeldung mit `AUTH_PASSWORD`.

Beim Start migriert die App die Datenbank und legt den Kategorienbaum an. Alles
Zustandsbehaftete liegt in `./data` (SQLite-Datei + Belege) — ein Backup ist eine
Kopie dieses Ordners.

## Was die App macht

| Bereich | Inhalt |
| --- | --- |
| **Erfassen** | Kamera, Datei, Drag & Drop, Einfügen aus der Zwischenablage, mehrere Bons gleichzeitig. Bild oder PDF, Typprüfung über Magic Bytes. |
| **Lesen** | Text-PDF → eingebauter Parser (ohne Modell). Foto/Scan → Vision-Modell. Bei Zweifel `Prüfen` statt Absturz. |
| **Korrigieren** | Kopfdaten und Positionen editierbar, Originalbeleg daneben, Summenabweichung wird angezeigt. |
| **Auswerten** | Monatsausgaben, Kategorien, Märkte, Artikel nach Ausgabe/Häufigkeit/Stückpreis, Anteil am Lebensmittelbudget, Preisverlauf, Vormonatsvergleich. |
| **Verwalten** | Kategorien hierarchisch pflegen (inkl. „zählt als Lebensmittel“), API-Tokens. |

Ausführlich: [`docs/konzept.md`](docs/konzept.md).

## Konfiguration

Alles über `.env` (Vorlage: [`.env.example`](.env.example)).

| Variable | Default | Bedeutung |
| --- | --- | --- |
| `AUTH_MODE` | `password` | `password`, `trusted_header` oder `none` — siehe unten |
| `AUTH_PASSWORD` | – | Passwort bei `AUTH_MODE=password` |
| `SECRET_KEY` | zufällig | Signiert das Session-Cookie. Ohne Wert sind Sessions nach einem Neustart ungültig |
| `COOKIE_SECURE` | `false` | `true`, sobald HTTPS davor steht |
| `AUTH_TRUSTED_HEADER` | `Remote-User` | Header, den der Proxy setzt (nur `trusted_header`) |
| `DATA_DIR` | `./data` | SQLite-Datei und Belege |
| `LLM_PROVIDER` | `none` | `none`, `openai`, `openrouter`, `ollama` |
| `LLM_MODEL` | – | z. B. `gpt-4o-mini`, `qwen2.5vl:7b` |
| `LLM_API_KEY` | – | Schlüssel des Providers (bei Ollama leer) |
| `LLM_BASE_URL` | providerabhängig | Nur setzen, wenn abweichend |
| `LLM_MAX_IMAGE_PX` | `1600` | Fotos werden vorher verkleinert — spart Tokens |
| `UPLOAD_MAX_BYTES` | `15728640` | 15 MB |
| `LOG_FORMAT` | `text` | `text` oder `json` |
| `WORKER_MAX_ATTEMPTS` | `3` | Wiederholungen je Extraktionsauftrag |

### Anmeldung

Drei Modi ([ADR-004](docs/entscheidungen.md#adr-004)):

* **`password`** (Default) — ein Passwort für den Haushalt, Session als
  httpOnly-Cookie. Der Login ist rate-limitiert.
* **`trusted_header`** — kein eigener Login: ein Reverse Proxy (Authelia,
  authentik, Traefik Forward-Auth) authentifiziert und setzt
  `AUTH_TRUSTED_HEADER`.
  > **Nur sicher, wenn der Proxy diesen Header überschreibt.** Tut er es nicht,
  > kann jeder Client ihn selbst mitschicken und ist damit angemeldet.
* **`none`** — kein Schutz. Nur für eine rein lokale Instanz.

### Texterkennung

Ohne Modell (`LLM_PROVIDER=none`) bleibt die App voll bedienbar: eBon-PDFs
werden gelesen, Fotos landen unter „Prüfen“ und werden von Hand erfasst.

Mit Modell werden auch Fotos gelesen. Der Prompt liegt als einzelne, editierbare
Datei unter [`backend/app/prompts/receipt_extraction.de.txt`](backend/app/prompts/receipt_extraction.de.txt).

```bash
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# Lokal per Ollama (kein Schlüssel nötig)
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5vl:7b
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Unter *Einstellungen → Systemzustand* steht, ob ein Modell einsatzbereit ist und
ob Aufträge in der Warteschlange hängen.

## iOS-Kurzbefehl

iOS erlaubt einer PWA kein Share-Target, deshalb der Umweg über einen
Kurzbefehl: einmal unter *Einstellungen → API-Tokens* ein Token erstellen (der
Klartext ist nur bei der Erstellung sichtbar), dann in der Kurzbefehle-App:

1. **Aktion:** „Inhalte und Web“ → *Inhalte von URL abrufen*
2. **URL:** `https://<deine-instanz>/api/receipts`
3. **Methode:** `POST`
4. **Header:** `Authorization` = `Bearer edb_…`
5. **Anfragetext:** `Formular` → Feld `file` (Typ *Datei*) = *Kurzbefehl-Eingabe*
6. Im Kurzbefehl-Detail „Im Teilen-Blatt anzeigen“ aktivieren, Eingabetyp
   *Bilder und Dateien*

Danach: Foto → Teilen → Kurzbefehl. Solche Uploads sind in der App als Quelle
`shortcut` erkennbar.

## Entwicklung

Voraussetzungen: [uv](https://docs.astral.sh/uv/), Node 22 mit pnpm
(`corepack enable`). **Keine Datenbank, kein Redis, kein Docker.**

```bash
make install
make check      # ruff · mypy strict · pytest · eslint · vue-tsc · vitest

make dev        # Terminal 1: API auf :8000
make dev-web    # Terminal 2: Vite mit Hot-Reload auf :5173
```

`make check` läuft in wenigen Sekunden und braucht nichts weiter — falls doch
etwas fehlt, ist das ein Fehler und kein Setup-Schritt.

```
backend/app/
  domain/       reine Logik: Geld, Normalisierung, Bon-Parser, Auswertung
  services/     Anwendungsfälle (DB, Dateien, Queue)
  integrations/ Außenwelt hinter Interfaces (LLM, Dateien, PDF/Bild)
  api/routes/   HTTP
frontend/src/
  styles/       Design-Tokens — die einzige Datei mit Farbwerten
  ui/           Primitives (Button, Card, Input, MoneyInput …)
  charts/       SVG-Diagramme ohne Abhängigkeit
  components/   zusammengesetzte Bausteine
  pages/        Seiten
```

Die harte Regel: `domain/` importiert **nichts** aus `services/`, `api/` oder
`integrations/`. Dort liegen Geldarithmetik, Normalisierung und alle
Aggregationen — und der Schwerpunkt der Tests.

## Dokumentation

| Datei | Inhalt |
| --- | --- |
| [`docs/konzept.md`](docs/konzept.md) | Was die App ist und was bewusst nicht |
| [`docs/architektur.md`](docs/architektur.md) | Wie sie gebaut ist |
| [`docs/entscheidungen.md`](docs/entscheidungen.md) | Jede Architekturentscheidung mit Begründung und Rücknahmepfad |
| [`docs/analyse.md`](docs/analyse.md) | Befunde am Vorgängerstand, mit Messwerten |
| [`docs/plan.md`](docs/plan.md) | Reihenfolge und Abnahmekriterien des Neuschnitts |

## Lizenz

GPL-3.0 — siehe [`LICENSE`](LICENSE).
