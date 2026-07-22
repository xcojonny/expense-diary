# Architektur

Quelle der Wahrheit für das *Wie*. Wer Datenmodell, Hintergrundjobs oder eine
Architekturentscheidung ändert, pflegt diese Datei in derselben Änderung.

## 1. Überblick

- **Backend:** FastAPI, SQLAlchemy 2 (async), PostgreSQL 16, Alembic. Async
  Extraktion über einen ARQ-Worker + Redis (ab Phase 2).
- **Frontend:** Nuxt 3 SPA (`ssr: false`), TypeScript strict, Pinia, Tailwind, PWA.
- **LLM:** provider-agnostischer Adapter (`integrations/llm/`), Default
  OpenAI-Vision-kompatibel, umschaltbar auf Ollama per ENV.
- **Betrieb:** docker-compose (db, redis, backend, worker, frontend).

### 1.1 Schichten & die eine harte Regel

`domain/` importiert **nichts** aus `services/`, `integrations/` oder `api/`.
Es ist reine, synchrone, I/O-freie Logik (Normalisierung, später Aggregation)
und dort konzentrieren sich die Unit-Tests. Alles mit DB-, Netz- oder
Redis-Zugriff gehört in `services/` bzw. `integrations/`.

`services/` orchestriert Use-Cases. `integrations/` kapselt jede Außenwelt
hinter einem Interface, damit Anbieter austauschbar bleiben (LLM: openai /
ollama / null-Fallback; Storage).

## 2. Datenmodell

UUID-v7-Primärschlüssel (zeitlich sortiert), `created_at`/`updated_at` per
Mixin. Geldbeträge als `Numeric` (keine Floats). Enums als Text-Spalte mit
`CHECK`-Constraint. Produktnamen für den Abgleich als `CITEXT`.

`Receipt` und `Item` gehören einer `GROUP` (Haushalt) — die Tenancy-Grenze
(siehe §6). `Category` ist geteilte Stammdaten (global). `LineItem` erbt die
Gruppe über sein `Receipt`.

```mermaid
erDiagram
    GROUP   ||--o{ RECEIPT : owns
    GROUP   ||--o{ ITEM : owns
    RECEIPT ||--o{ LINE_ITEM : has
    ITEM    ||--o{ LINE_ITEM : "aggregates (via normalized_name)"
    CATEGORY ||--o{ LINE_ITEM : categorizes
    CATEGORY ||--o{ ITEM : categorizes
    CATEGORY ||--o{ CATEGORY : "parent/child"

    GROUP {
        uuid id PK
        text name
    }
    RECEIPT {
        uuid id PK
        uuid group_id FK
        text store_name
        timestamptz purchased_at
        numeric total
        text currency
        text status "uploaded|processing|done|needs_review|failed"
        text image_path
        text raw_ocr_text
        text confidence
        text error
    }
    LINE_ITEM {
        uuid id PK
        uuid receipt_id FK
        uuid item_id FK
        uuid category_id FK
        text name
        citext normalized_name
        numeric quantity
        text unit
        numeric unit_price
        numeric total_price
        text vat_class
        text line_type "product|deposit|discount"
    }
    ITEM {
        uuid id PK
        uuid group_id FK
        citext normalized_name "UK per group"
        text display_name
        uuid category_id FK
    }
    CATEGORY {
        uuid id PK
        text name
        uuid parent_id FK
        int sort_order
    }
```

### 2.1 Receipt-Statusfluss

```mermaid
stateDiagram-v2
    [*] --> uploaded: Upload speichert Datei + Receipt
    uploaded --> processing: Worker nimmt Job
    processing --> done: Extraktion ok, Summen plausibel
    processing --> needs_review: Extraktion ok, aber prüfen (Summe weicht ab / confidence niedrig)
    processing --> failed: Fehler (LLM/IO)
    needs_review --> done: manuell korrigiert
```

Das Frontend pollt den Receipt (~2 s), bis `processing` verlassen ist
(Entscheidung: Polling statt WebSocket — das Backend bleibt zustandslos).

### 2.2 Normalisierung (`domain/normalize.py`)

Der Schlüssel für Vergleichbarkeit über Bons und Zeit: `normalize_name`
faltet Groß/Klein, Umlaute/ß, Akzente, Dezimal-Komma und Satzzeichen zu einem
stabilen Key. „H-Milch 3,5%", „H MILCH 3.5" und „h.milch 3,5 %" ergeben denselben
`normalized_name`. `LineItem.normalized_name` und `Item.normalized_name` nutzen
dieselbe Funktion; darüber mappen Positionen auf das `Item`-Stammdatum für
Trends. Bewusst einfach — ein klügerer Matcher kann später aufsetzen, ohne den
Vertrag zu ändern.

## 3. Extraktions-Pipeline (Phase 2, implementiert)

1. `POST /api/v1/receipts` validiert Größe (`UPLOAD_MAX_BYTES`) und Typ per
   **Magic-Bytes** (`domain/upload.detect_media_type`, nicht dem
   Client-Content-Type vertrauend), speichert die Datei unter einem
   server-generierten Namen (`integrations/storage/local`) und legt `Receipt`
   mit `status=uploaded` an.
2. Die Extraktion wird eingeplant: bevorzugt als **ARQ-Job**
   (`workers/tasks.extract_receipt_task`); ist kein Redis/Worker verfügbar,
   fällt der Endpoint auf **FastAPI BackgroundTasks** zurück (beides laut Brief
   erlaubt). Der Job setzt `status=processing`.
3. `services/extraction_service` liest die Datei (PDF → erstes eingebettetes
   Bild via `integrations/storage/pdf`), schickt sie über den Vision-Adapter
   (`integrations/llm`) mit dem Prompt aus `prompts/receipt_extraction.de.txt`
   und übergibt die rohe Antwort dem **reinen** Parser
   (`domain/extraction.parse_receipt_json`).
4. Ergebnis → `Receipt` + `LineItem`s; Produkt-Positionen bekommen
   `normalized_name` und werden pro Gruppe auf `Item` gemappt (Trend-Anker),
   Deposit/Discount bleiben receipt-lokal. `domain/extraction.reconcile_confidence`
   vergleicht die Positionssumme mit `total`: passt sie → `status=done`, sonst
   (oder bei `confidence=low` / keinen Positionen) → `needs_review`.
5. Jeder Fehler wird als `status=failed` mit `error` festgehalten (ein defekter
   Bon legt den Worker nicht lahm). `LLM_PROVIDER=none` (kein Modell) →
   `raw=None` → `needs_review` (manuelle Erfassung). Jeder LLM-Pfad degradiert
   sauber auf den No-op-Fallback.

Das Frontend (`pages/upload.vue` + `composables/useReceiptPolling`) pollt nach
dem Upload `GET /api/v1/receipts/{id}` (~2 s), bis ein Endzustand erreicht ist.

### 3.1 Manuelle Korrektur (Phase 3)

`pages/bon/[id].vue` erlaubt das Editieren von Kopf und Positionen
(PATCH/POST/DELETE unter `/receipts/{id}` bzw. `/line-items`). Namens- oder
Typänderungen laufen serverseitig durch dieselbe `services/items.apply_product_mapping`
wie die Extraktion — eine korrigierte Position landet also am selben Item-Trend-Anker
wie eine extrahierte, `normalized_name`/`item_id` werden nie vom Client gesetzt.
„Als geprüft markieren" setzt `needs_review → done`.

## 4. Analyse-Ebene (Phase 4, das Herzstück — implementiert)

Architektur: `services/analytics_service` holt die relevanten Positionen als
flache `PurchaseRecord`s (Join `line_items`×`receipts`×`categories`×`items`,
Zeitfenster per `coalesce(purchased_at, created_at)`). Die **reine** Rechenlogik
liegt in `domain/aggregation` und ist der Testschwerpunkt (Unit-Tests ohne DB).

Endpoints unter `/api/v1/analytics` (alle gruppen-scoped, Monat per `?year=&month=`,
Default = laufender Monat):

- `GET /monthly` — Gesamtausgaben, Produkt/Pfand/Rabatt-Summen, Bon-Anzahl,
  Aufschlüsselung nach Kategorie und Store, Top-N teuerste Einzelpositionen.
- `GET /overbought` — Artikel nach Häufigkeit (dann Ausgabe): „was kaufe ich zu viel".
- `GET /expensive` — Artikel nach Gesamtausgabe **und** nach Ø-Stückpreis, plus
  Anteil am Lebensmittelbudget (`is_food` schließt Nicht-Lebensmittel-Kategorien aus).
- `GET /price-trend/{item_id}` — Ø-Stückpreis pro Tag über die Zeit (für den Chart).
- `GET /compare` — Vormonatsvergleich (Gesamt + je Kategorie, Delta + Prozent).

Frontend: `pages/bericht.vue` mit Monatsnavigation, Kategorie-/Store-Balken,
Listen und einem abhängigkeitsfreien SVG-Preisverlauf (`components/TrendChart.vue`)
— ein Artikel-Klick lädt dessen Trend. Geldbeträge kommen als Strings (Decimal)
und werden per `utils/format` formatiert.

Beträge: Geld als `Numeric`/`Decimal`; JSON serialisiert Decimals als String, das
Frontend formatiert (kein Float-Rundungsfehler).

## 5. Offene Entscheidungen

- Kategorie-Hierarchie: geseedet (Top-Level = die vom Prompt vergebenen
  Kategorien, plus einige Unterkategorien) und via CRUD verwaltbar (Phase 5,
  siehe §7). Tiefe ist nicht begrenzt.
- Session-Härtung ist auf cooking-jonelli-Niveau: browser-gebundene Magic-Links
  mit Pairing-Codes, Redis-Rate-Limits und Refresh-Reuse-Detection (Family-Kill).
  Siehe §6.1.

## 7. Kategorien-Verwaltung (Phase 5)

Kategorien sind geteilte Stammdaten (nicht gruppen-scoped). CRUD unter
`/api/v1/categories` (`POST`/`PATCH`/`DELETE`), Logik in `services/category_service`:

- Doppelte Namen innerhalb desselben Elternteils werden abgelehnt (400) — der
  Self-FK allein erzwingt das bei `parent_id IS NULL` nicht (NULLS DISTINCT).
- Zyklen beim Umhängen werden abgelehnt (400): eine Kategorie kann nicht
  Nachfahre ihrer selbst werden.
- Beim Löschen werden Unterkategorien zu Top-Level (`parent_id` FK SET NULL) und
  Positions-/Item-Verweise auf `NULL` gesetzt — keine Kaskadenlöschung von Daten.

Frontend: `pages/kategorien.vue` (anlegen, umbenennen, umhängen, löschen). Die
manuelle Positions-Korrektur (Phase 3) nutzt dieselbe Kategorienliste im
Bon-Detail-Dropdown.

## 6. Multi-Tenancy & Auth (implementiert)

Die **Gruppe (Haushalt)** ist die Mandantengrenze. Nutzer gehören über
`group_members` (Rolle `admin`/`member`) einem oder mehreren Haushalten an.

- `receipts.group_id` und `items.group_id` (NOT NULL, `ON DELETE CASCADE`);
  `items` sind **pro Gruppe** eindeutig (`unique(group_id, normalized_name)`) —
  jeder Haushalt hat seinen eigenen Produktkatalog / Preisverlauf.
- **Tenancy-Seam** `api/deps.get_current_group_id`: leitet die aktive Gruppe aus
  dem `X-Group-Id`-Header ab (Mitgliedschaft vorausgesetzt), sonst die früheste
  Mitgliedschaft. Jeder gruppen-behaftete Endpoint hängt daran — Gruppenwechsel
  ist ein Header, Auth bleibt an einer Stelle.
- Governance (`require_group_admin`): Einladungen erfordern Admin der aktiven Gruppe.
- Bootstrap: `INITIAL_ADMIN_EMAIL` wird beim Start als aktiver Instanz-Admin +
  Besitzer der Default-Gruppe angelegt (`auth_service.ensure_initial_admin`).
  Neue Nutzer ohne Einladung erhalten einen eigenen Haushalt (`ensure_personal_group`).

### 6.1 Login-Flüsse

Kein Passwort. Zwei Wege, beide stellen die **App-eigene** Session aus
(kurzlebiges JWT-Access-Token im Speicher + rotierendes Refresh-Token als
httpOnly-Cookie, hash-gespeichert, `/auth/refresh` rotiert, `/auth/logout` widerruft).
**Refresh-Reuse-Detection:** jede Rotation gehört zu einer `family_id`; wird ein
bereits rotiertes Token erneut vorgezeigt, wird die ganze Familie widerrufen
(Diebstahl-Abwehr) — Ausnahme ist ein kurzes Grace-Fenster
(`REFRESH_REUSE_GRACE_SECONDS`) für Parallel-Tab-Rotationsraces, solange die
Familie noch ein lebendes Token hat.

- **Magic-Link** (`/auth/magic-link` → Mail → `/auth/verify`): Single-Use,
  kurzlebig, **browser-gebunden** (Claude.ai-Prinzip). `/auth/magic-link` setzt
  ein stabiles `login_request`-Cookie (nur dessen Hash landet am Token). Öffnet
  man den Link im selben Browser → Session; woanders → `{status:"code", code}`,
  und der ursprüngliche Browser schließt über `/auth/verify-code` ab (der Code
  steht nie in der Mail, nur auf der Verify-Seite; nutzlos ohne das Cookie,
  5 Fehlversuche pro Token, IP-Rate-Limit, HMAC-abgeleitet — nie gespeichert).
  Die Login-Seite pollt `/auth/login-status`. Kein User-Enumeration (immer 202,
  Redis-Rate-Limits pro E-Mail/IP). Mail via SMTP; ohne `SMTP_HOST` loggt der
  Mailer den Link (Dev).
- **OIDC / Authelia** (`/auth/oidc/login` → Authelia → `/auth/oidc/callback`):
  Authorization-Code-Flow mit vertraulichem Client (`services/oidc_service`),
  State-Cookie gegen CSRF, Userinfo über TLS. `upsert_oidc_user` verknüpft
  `(issuer, subject)` → lokaler User (Anlage bei Erstlogin).
- **Einladungen** (`/groups/invitations` → Mail → `/auth/invitations/accept`):
  legt/aktiviert den User und die Mitgliedschaft an.

Frontend: `stores/auth` (Bootstrap via `/auth/refresh`), globaler Route-Guard,
`pages/login.vue` (Magic-Link + SSO-Button + Token/Invite/SSO-Callback),
`GroupSwitcher` (Header) und `pages/gruppe.vue` (Haushalte, anlegen, einladen).

### 6.2 Authelia als OIDC-Client

In Authelias `identity_providers.oidc.clients` einen vertraulichen Client anlegen:

```yaml
- client_id: expense-diary
  client_secret: '<hash oder plaintext gemäß Authelia-Version>'
  redirect_uris:
    - https://haushaltsbuch.example.org/api/v1/auth/oidc/callback
  scopes: [openid, email, profile]
  grant_types: [authorization_code]
  response_types: [code]
```

Backend-ENV: `OIDC_ISSUER=https://auth.example.org`, `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET` (siehe `.env.example` im Repo-Root).

## 8. Release & Deployment

`.github/workflows/release.yml` baut nach grüner CI auf `main` (sowie auf
`v*`-Tags / manuell) die Images `ghcr.io/<owner>/expense-diary-{backend,frontend}`
(Tags `latest`, `sha-<sha>`, bei Tags `semver`) und schiebt sie nach GHCR; das
Git-SHA wird als `GIT_SHA` eingebacken (`/api/v1/version`).

**Pull-Deploy per Webhook** (wie cooking-jonelli, `webhook/`): der
`deploy`-Job schickt nach grüner CI einen **HMAC-SHA256-signierten**
`{sha, timestamp}`-Body an `DEPLOY_WEBHOOK_URL` (`X-Hub-Signature-256`, verifiziert
gegen `DEPLOY_WEBHOOK_SECRET`). Der [`webhook`](https://github.com/adnanh/webhook)-
Container ruft `deploy.sh` auf: Replay-Schutz (>5 min verworfen), `flock`,
`IMAGE_TAG=sha-<commit>` in der App-`.env`, `docker compose pull && up -d --wait`,
**Auto-Rollback** auf den vorherigen Tag bei nicht-healthy Zustand, optionale
ntfy-Benachrichtigung. Ohne gesetzte Secrets ist der Deploy-Job ein No-op.
Reverse-Proxy davor für TLS + Routing `/api`,`/media` → Backend, Rest → Frontend.
Details: `DEPLOY.md`.
