# Plan für den Neuschnitt

Reihenfolge und Abnahmekriterien. Was hier abgehakt ist, ist im Repo umgesetzt
und verifiziert — der Status am Ende jeder Phase nennt die Prüfung.

## Phase 0 — Analyse & Konzept ✅

Altstand vermessen (nicht geraten): Lint, Typecheck, Migrationen, Test-Suite
mit und ohne Redis laufen lassen, UI-Dateien lesen, Deployment zählen.
Ergebnis: [`analyse.md`](analyse.md), [`konzept.md`](konzept.md),
[`entscheidungen.md`](entscheidungen.md).

**Abnahme:** Jeder Kritikpunkt in `analyse.md` ist mit Datei, Zeile oder
Messwert belegt.

## Phase 1 — Fundament: ein Prozess, eine Datei ✅

- SQLite + WAL, `aiosqlite`, `PRAGMA foreign_keys=ON` (SQLite erzwingt FKs
  sonst nicht!), Alembic für Upgrades.
- Datenmodell mit **ganzzahligen Cent** und `quantity_milli` (Tausendstel) —
  keine Fließkommazahl auf dem Weg.
- `is_food` als Spalte an `Category`.
- `core/config.py` mit flacher, dokumentierter ENV-Liste.
- Logging auf stdout (strukturiert), kein Log-Ring, kein Redis.

**Abnahme:** `alembic upgrade head` und `downgrade base` laufen sauber durch;
Modelle sind mit mypy strict typisiert.

## Phase 2 — Domäne: die reine Logik ✅

Übernommen und auf Cent umgestellt, weil hier der Wert des Projekts liegt:

- `domain/money.py` — **neu.** Parsen deutscher Beträge nach Cent, Summen,
  Toleranzvergleich. Die eine Stelle, an der Geld interpretiert wird.
- `domain/normalize.py` — unverändert übernommen (der Trend-Schlüssel).
- `domain/extraction.py` — eBon-Textparser + JSON-Parser, auf Cent umgestellt.
- `domain/aggregation.py` — Monatsbericht, Artikel-Ranking, Preistrend,
  Vergleich; `is_food` kommt jetzt als Flag am Record, nicht aus einer
  Namensliste.

Harte Regel bleibt: `domain/` importiert nichts aus `services/`, `api/`,
`integrations/`. Hier liegt der Schwerpunkt der Unit-Tests.

**Abnahme:** Unit-Tests decken Cent-Parsing, Normalisierung, beide
Extraktionswege und alle Aggregationen ab — ohne Datenbank.

## Phase 3 — Extraktion ohne Redis ✅

- `models/job.py` + `services/jobs.py`: DB-gestützte Queue (`queued → running
  → done | failed`), atomares Claiming, Retries mit Backoff.
- `worker.py`: asyncio-Task im API-Prozess, geweckt über ein `asyncio.Event`
  (kein Poll-Delay beim Upload), sauberer Shutdown.
- **Crash-Recovery:** beim Start werden in `running` hängende Jobs requeued.
- `integrations/llm/`: Adapter-Protokoll, OpenAI-/OpenRouter-kompatibel,
  Ollama, `none`. Ein *konfigurierter, aber unbrauchbarer* Provider wird laut
  geloggt statt still auf No-op zu fallen.
- Fehlertext landet am Bon (`error`), wo man ihn sucht — nicht in einem
  Admin-Log-Ring.

**Abnahme:** Upload → Statuswechsel → Positionen, in einem
Integrationstest ohne externe Dienste. Ein defekter Bon setzt `failed` und
blockiert die Queue nicht.

## Phase 4 — API ✅

- Auth: `AUTH_MODE = password | trusted_header | none`, HMAC-signiertes
  Session-Cookie, API-Tokens (`edb_`, nur als SHA-256-Hash gespeichert).
- Endpoints unter `/api`: `receipts`, `line-items`, `categories`, `analytics`,
  `tokens`, `auth`, `health`.
- Artikel-Ranking als **ein** Endpoint mit `sort=frequency|spend|unit_price`
  statt zwei getrennten (`/overbought`, `/expensive`).
- Alle Beträge als `*_cents` (Integer) im JSON.
- In-Process-Rate-Limit auf dem Login (kein Redis).

**Abnahme:** Integrationstests über die ganze API gegen eine
temporäre SQLite-Datei; kein laufender Dienst nötig.

## Phase 5 — Frontend: Design-System zuerst ✅

Reihenfolge ist bewusst: erst Tokens und Primitives, dann Seiten. Die
Utility-Ketten-Duplikation des Altstands entstand, weil es umgekehrt lief
([ADR-011](entscheidungen.md#adr-011)).

1. **Tokens** (`styles/tokens.css`): Farben, Flächen, Radien, Schatten,
   Chart-Palette — je für Light und Dark. Keine Farbe direkt in einer
   Komponente.
2. **Primitives** (`ui/`): Button, Card, Badge, Field, Input, Select,
   MoneyInput, Modal, Skeleton, Empty, Toasts, Stat, Segmented, Icon.
3. **Charts** (`charts/`, handgeschriebenes SVG, keine Abhängigkeit):
   ChartDonut (Kategorien), ChartLine (Preisverlauf mit Achsen und Hover),
   ChartBars (Ranglisten).
4. **Shell**: Sidebar auf Desktop, Bottom-Nav + Kamera-Knopf auf Mobil,
   Theme-Umschalter, Toast-Host.
5. **Seiten**: Übersicht, Bon erfassen, Bons, Bon-Detail, Bericht, Kategorien,
   Einstellungen, Login, 404.

Datenladen über `useResource` — **pro Widget**, mit eigenem Skeleton- und
Fehlerzustand und Retry-Knopf. Kein `Promise.all`, das eine ganze Seite
mitreißt.

**Abnahme:** Kein Hex-Farbwert außerhalb von `tokens.css`; Dark Mode
vollständig; jede Liste hat Empty State und Fehlerzustand; Geld ausschließlich
über `formatCents`.

## Phase 6 — Betrieb & Verifikation ✅

- **Ein** Dockerfile (Multi-Stage: SPA bauen → Python-Runtime, die API *und*
  die gebaute SPA ausliefert). Non-root, Healthcheck.
- `docker-compose.yml` mit **einem** Service und einem Volume.
- Migrationen laufen beim Start automatisch (kein `migrate`-Container).
- Makefile, CI (ruff, mypy strict, pytest, eslint, vue-tsc, vitest).

**Abnahme:** `make check` grün **ohne** externe Dienste; App startet, Login,
Upload, Bericht real durchgeklickt und per Screenshot belegt.

## Phase 7 — Mehrbenutzerbetrieb ✅

Nachgezogen, nachdem der Mehrbenutzerbetrieb doch gewünscht war. Leitlinie:
getrennte Daten ja, selbstgebaute Anmeldung nein
([ADR-004](entscheidungen.md#adr-004)).

1. **Datenmodell**: `households`, `household_members` (Rollen `admin`/`member`),
   `invitations`, `users` ohne Passwortspalte, `oidc_identities` mit
   `UNIQUE (issuer, subject)`. `receipts` und `items` bekommen
   `household_id NOT NULL`; `items` zusätzlich
   `UNIQUE (household_id, normalized_name)`. Kategorien bleiben global
   ([ADR-012](entscheidungen.md#adr-012)).
2. **Migration** `0002_households`: Spalten erst nullable, Backfill eines
   Default-Haushalts nur wenn Daten existieren, dann `NOT NULL`. Der Downgrade
   verweigert, sobald mehr als ein Haushalt da ist — lieber ein klarer Abbruch
   als stille Datenvermischung.
3. **Mandantenschnitt**: `require_user` → `require_household` →
   `require_household_admin`. Jede Abfrage auf Bons, Positionen, Artikel und
   Auswertungen filtert nach `household_id`; fremde IDs geben 404.
4. **OIDC**: Authorization-Code-Flow mit Discovery, `state`-Cookie und
   `userinfo` statt JWKS ([ADR-014](entscheidungen.md#adr-014)).
5. **Einladungen**: Token-Link mit Ablauf, Mailversand über `smtplib` im Thread,
   ohne SMTP wird der Link zurückgegeben
   ([ADR-013](entscheidungen.md#adr-013)).
6. **Frontend**: Haushaltswechsler in Sidebar und Topbar, Haushaltsseite
   (Name, Mitglieder, Rollen, Einladungen, weiterer Haushalt, löschen),
   SSO-Knopf auf der Anmeldeseite, Seite zum Einlösen einer Einladung.

**Abnahme:** `test_tenancy.py` prüft **jeden** Endpoint mit Mandantenbezug auf
Trennung — nicht nur ein Beispiel. Dazu Rollen- und Einladungstests
(`test_households.py`), OIDC gegen eine Provider-Attrappe (`test_oidc.py`) und
Frontend-Tests für Wechsler, SSO-Maske und Einladungsseite.

## Bewusst nicht gemacht

- **Kein Datenmigrationspfad vom Altstand.** PR #1 ist nicht gemerged, das
  Schema hat nie produktiv Daten gehalten. Ein Migrationsskript für
  Postgres→SQLite wäre Aufwand für einen leeren Datensatz. Falls doch Daten
  existieren: hier melden, das ist ein überschaubares Skript.
- **Keine Icon-Bibliothek als Abhängigkeit.** Die verwendeten Icons sind Inline-SVG
  (~20 Stück). Spart eine Abhängigkeit und Bundle-Größe.
- **Kein E2E-Framework.** Bei dieser Größe zahlen sich Integrationstests auf der
  API plus Komponententests besser aus als eine Playwright-Suite.
