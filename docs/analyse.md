# Analyse des Altstands

Ausgangslage: Der Code lag nicht auf `main`, sondern auf dem offenen PR #1
(Branch `claude/haushaltsbuch-setup-p1krp5`) — 153 Dateien, ~24.400 Zeilen.
Diese Datei hält fest, *was* nicht sauber lief und *warum*, mit Messwerten.
Sie ist die Begründung für den Neuschnitt in [`konzept.md`](konzept.md).

## 1. Was gut war (und übernommen wurde)

Drei Module tragen den eigentlichen Wert des Projekts. Sie sind rein, I/O-frei
und getestet — sie wurden übernommen und nur auf Cent-Arithmetik umgestellt:

| Modul | Warum wertvoll |
| --- | --- |
| `domain/normalize.py` | Faltet „H-Milch 3,5 %“ / „H MILCH 3.5“ auf einen Schlüssel. Das ist die Voraussetzung für Preisverläufe überhaupt. |
| `domain/extraction.py` | LLM-freier Parser für deutsche eBon-PDFs (REWE, Lidl, Kaufland …) mit Pfand-/Rabatt-Erkennung. Löst den Normalfall ohne Modellkosten. |
| `domain/aggregation.py` | Monatsbericht, „zu viel gekauft“, „teure Lebensmittel“, Preistrend, Vormonatsvergleich. Das Herzstück. |

Ebenfalls solide: die Schichtenregel („`domain/` importiert nichts aus
`services/`“), der Extraktions-Prompt als editierbare Datei, ruff + mypy strict
(beide liefen fehlerfrei) und die Alembic-Migrationen (Round-Trip geprüft).

## 2. „Läuft nicht sauber“ — die Messwerte

### 2.1 `make check` schlägt auf dem dokumentierten Setup fehl

Reproduziert:

```
make dev-up      # startet Redis auf Host-Port 56379
make test        # tests/conftest.py: REDIS_URL default = redis://localhost:6379/1
→ 2 failed, 85 passed
   FAILED tests/integration/test_ratelimit.py::test_blocks_after_limit
   FAILED tests/integration/test_ratelimit.py::test_rearms_key_without_ttl
```

Ursache: drei Quellen widersprechen sich beim Redis-Port.

| Datei | Port |
| --- | --- |
| `docker-compose.dev.yml` (via `make dev-up`) | `56379` |
| `backend/.env.example` | `56379` |
| `backend/tests/conftest.py` | **`6379`** |

`conftest.py` setzt die Variablen mit `os.environ.setdefault`, und
Umgebungsvariablen haben in pydantic-settings Vorrang vor `.env` — die `.env`
wird im Test also nie gelesen. Mit korrigiertem Port: `2 passed in 1.91s`.

### 2.2 Fehlendes Redis verlangsamt alles um Faktor 12

Nicht „best-effort-Degradation“, wie `docs/architecture.md` §3.2 behauptet,
sondern Retry-Timeouts auf jedem Request:

| Lauf | Ergebnis |
| --- | --- |
| Redis nicht erreichbar | `2 failed, 85 passed in 261.67s` |
| Redis erreichbar | `87 passed in 22.00s` |

Redis war an drei Stellen eingebaut (ARQ-Queue, Rate-Limits, Log-Ring), aber
nur eine davon war dokumentiert optional. Im Betrieb heißt das: ein
Redis-Schluckauf macht die App nicht funktional kaputt, sondern *langsam* —
die unangenehmere Fehlerart, weil nichts alarmiert.

### 2.3 Test-Suite koppelt an die Umgebung

`tests/integration/conftest.py` hat ein `autouse`-Fixture, das **vor jedem
Test** `DELETE FROM groups/users/categories` ausführt und den kompletten
Kategorienbaum neu seedet; `app_client` baut zusätzlich pro Test die App via
`create_app()` plus vollen Lifespan auf. Dazu braucht die Suite ein laufendes
Postgres **und** Redis. Ergebnis: kein Test läuft ohne Infrastruktur, und die
Rückkopplung beim Entwickeln ist zäh.

### 2.4 Neun Dienste für einen Haushalt

`docker-compose.yml` (195 Zeilen) definiert: `db`, `redis`, `migrate`,
`backend`, `worker`, `frontend`, `docker-socket-proxy`, `deploy-webhook` — plus
`webhook/deploy.sh` (107 Zeilen Bash mit HMAC-Verifikation, Replay-Schutz,
`flock`, Auto-Rollback). Jeder Dienst ist ein eigener Fehlermodus, und keiner
davon trägt zur Kernfunktion bei.

### 2.5 Scope-Drift gegen die eigenen Anforderungen

`docs/anforderungen.md` listet als **Nicht-Ziel**:

> Kein Multi-User-/Gruppen-Modell (privates Homelab, ein Haushalt).

Implementiert war trotzdem: Gruppen, Mitgliedschaften mit Rollen, Einladungen
per Mail, OIDC-Client für Authelia, Magic-Links mit Browser-Bindung und
Pairing-Codes, Refresh-Token-Familien mit Reuse-Detection und Grace-Fenster,
Instanz-Admin, Admin-Log-Ansicht. Zusammen rund **1.500 der 4.790
Backend-Zeilen** — knapp ein Drittel des Backends für ein ausdrücklich
gestrichenes Feature. Diese Zeilen erklären auch, warum Redis, SMTP und der
Log-Ring überhaupt gebraucht wurden.

> **Nachtrag.** Der Mehrbenutzerbetrieb ist inzwischen ausdrücklich **gewollt**
> und umgesetzt ([ADR-004](entscheidungen.md#adr-004)). Der Befund oben bleibt
> trotzdem gültig — er richtet sich gegen den *Umfang*, nicht gegen das Feature:
> Magic-Links mit Browser-Bindung, Pairing-Codes und Refresh-Token-Familien mit
> Reuse-Detection waren der teure Teil und sind auch in der neuen Fassung
> draußen. Getrennte Daten pro Haushalt sind eine Datenmodell-Frage und kosten
> eine Spalte plus eine Dependency; die Anmeldung selbst delegieren wir an einen
> Identity Provider oder den Proxy.

### 2.6 Geld als String über die API

Beträge lagen als `Numeric` in der DB und wurden als JSON-**String**
serialisiert. Folge: jede Frontend-Datei parste selbst zurück. `pages/index.vue`
brachte eigene `num()`/`eur()`-Helfer mit — obwohl `utils/format.ts` genau das
schon exportiert:

```ts
// pages/index.vue — Duplikat mit eigener Rundung
const num = (v) => { const n = parseFloat(String(v ?? '').replace(',', '.')); … }
```

Jede solche Stelle ist ein potenzieller Rundungsfehler an der UI-Grenze.

### 2.7 `is_food` bricht beim Umbenennen

`domain/aggregation.py` entscheidet über eine hartkodierte Namensliste, was
Lebensmittel sind:

```python
NON_FOOD_CATEGORIES = frozenset({"Haushalt & Reinigung", "Drogerie & Körperpflege", …})
```

Phase 5 erlaubt aber das Umbenennen von Kategorien. Wer „Drogerie &
Körperpflege“ zu „Drogerie“ macht, zählt sie ab dann stillschweigend zum
Lebensmittelbudget — und die Kennzahl „Anteil am Lebensmittelbudget“ ist falsch,
ohne dass irgendwo ein Fehler auftaucht.

## 3. „UI/UX ist nicht cool“ — die Befunde

Das Frontend hat **2.203 Zeilen für 11 Seiten und 2 Komponenten**
(`TrendChart`, `GroupSwitcher`). Es gibt kein Design-System.

| Befund | Belegstelle |
| --- | --- |
| **Kein Design-System.** `rounded border bg-white p-4` steht rund 30× wortgleich im Code; Farben (`bg-green-600`, `text-gray-500`) sind überall hartkodiert. `main.css` enthält genau eine Zeile: `@import 'tailwindcss'`. | alle Seiten |
| **Desktop ist eine schmale Spalte.** `max-w-3xl` = 768 px Inhaltsbreite für eine Analyse-App. | `app.vue:53` |
| **Navigation ist eine Linkliste.** 7 Text-Links, die auf Mobil umbrechen; kein Active-State, keine Icons, keine Bottom-Navigation — obwohl die App als PWA installierbar sein soll. | `app.vue:35-51` |
| **Der Hauptflow ist ein nacktes `<input type="file">`.** Kein `capture="environment"` (Kamera), kein Drag & Drop, keine Vorschau, kein Mehrfach-Upload, kein Fortschritt. Für „Bon abfotografieren“ als Kernaufgabe ist das die schwächste Stelle der App. | `pages/upload.vue:56-62` |
| **Ein Fehler leert die ganze Seite.** Dashboard und Bericht laden per `Promise.all` über 3 bzw. 4 Endpoints; fällt einer aus, ist alles leer. `bericht.vue` destrukturiert `error` nicht einmal — die Seite bleibt dann dauerhaft weiß. | `index.vue:7-13`, `bericht.vue:27-44` |
| **Kein Dark Mode, keine Skeletons, kein Toast-System.** Ladezustand ist der Text „Lädt …“; Feedback ist ein pro Seite handgebauter `notice`-Ref. | `index.vue:77`, `bon/[id].vue:102` |
| **Das „Herzstück“ sieht nicht danach aus.** Die Analyse-Ebene wird als `div`-Balken und Textlisten gerendert, mit genau einem Chart (59 Zeilen SVG). | `bericht.vue`, `TrendChart.vue` |
| **PWA ohne Icons.** Das Manifest deklariert `theme_color` und `display: standalone`, aber keine Icons — in `public/` liegt nur `favicon.svg`. Der Installations-Dialog bleibt kaputt. | `nuxt.config.ts:66-77` |
| **Entwickler-Text in der UI.** „Keine Positionen erkannt — bitte manuell erfassen (kommt in Schritt 5).“ | `pages/upload.vue:93` |
| **Monolithische Seiten.** `pages/bon/[id].vue`: 498 Zeilen, 20 Funktionen, inklusive eigenem Flash-System und Blob-Handling. | `pages/bon/[id].vue` |
| **Frontend praktisch untestet.** 4 Tests, beide Dateien testen reine Utils (`models`, `routing`). Keine Komponententests, kein Test für Geldformatierung oder API-Schicht. | `tests/` |

Nuxt war zudem auf `ssr: false` konfiguriert: kein SSR, keine Server-Routes,
keine Nitro-Nutzung — der volle Nuxt-Werkzeugkasten für eine reine SPA, die
hinterher von einem separaten nginx-Container ausgeliefert wurde.

## 4. Kernaspekte — was das Projekt eigentlich ist

Nach dem Durchstich bleibt ein sehr klarer Kern übrig:

1. **Ein Foto rein, strukturierte Positionen raus.** Erledigt ein Parser (bei
   eBons) oder ein Vision-LLM (bei Fotos). Standardproblem, muss nur
   zuverlässig sein und bei Zweifel in die manuelle Korrektur laufen.
2. **Normalisierung als Achse.** Ohne stabilen Produktschlüssel gibt es keinen
   Preisverlauf. Das ist die eine Stelle, an der Sorgfalt sich auszahlt.
3. **Die Analyse-Ebene ist das Produkt.** „Was ist teuer, was kaufe ich zu oft,
   was wird teurer“ — dafür existiert die App. Alles andere ist Zulieferung.
4. **Ein Haushalt, selbst gehostet.** Ein Nutzer, wenige Bons pro Tag, ein
   Server im Keller. Diese Betriebsgröße erlaubt radikal einfachere Technik als
   gewählt wurde.

Punkte 1–3 waren gut umgesetzt. Punkt 4 wurde ignoriert — daraus entstanden
Redis, ARQ, Postgres, neun Container, Gruppen und OIDC. Genau hier setzt der
Neuschnitt an.
