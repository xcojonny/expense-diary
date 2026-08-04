# Entscheidungen (ADRs)

Jede Entscheidung, die den Neuschnitt prägt: Kontext, Wahl, Konsequenz und —
wichtig — wie sie sich zurücknehmen lässt.

---

## ADR-001 — SQLite statt Postgres {#adr-001}

**Kontext.** Ein Haushalt, ein Nutzer, ~50 Bons im Monat, wenige MB im Jahr.
Der Altstand nutzte Postgres 16 mit `CITEXT`, dazu einen `migrate`-Container.

**Entscheidung.** SQLite im WAL-Modus, über `aiosqlite`. Alembic bleibt.

**Warum.** Die Last rechtfertigt keinen Datenbankserver. SQLite kippt hier auf
die *robustere* Seite: Backup ist `cp haushalt.db*`, es gibt keinen zweiten
Prozess, der nicht starten kann, keine Verbindungspools, keine Version-Drift
zwischen Server und Client. `CITEXT` wird nicht gebraucht, weil
`normalize_name` bereits kleinschreibt — die Groß-/Kleinschreibung ist zum
Zeitpunkt des Vergleichs schon gefaltet.

**Konsequenzen.**
- Genau ein Schreiber. Für einen Haushalt kein Thema, und der Worker läuft
  ohnehin im selben Prozess ([ADR-002](#adr-002)).
- `PRAGMA foreign_keys=ON` muss **pro Verbindung** gesetzt werden — SQLite
  erzwingt Fremdschlüssel sonst nicht. Passiert in `db/session.py` über einen
  `connect`-Event-Listener.
- `busy_timeout=5000`, damit ein paralleler Lesezugriff nicht sofort mit
  „database is locked“ abbricht.
- Alembic-Migrationen brauchen `render_as_batch=True` (SQLite kann kein
  `ALTER COLUMN`).

**Zurücknehmen.** SQLAlchemy abstrahiert den Dialekt; nötig wären eine
Migration und ein anderer `DATABASE_URL`. Zwei Stellen sind dialektspezifisch
und im Code markiert: der `connect`-Listener und `render_as_batch`.

---

## ADR-002 — DB-Queue im API-Prozess statt Redis + ARQ + Worker-Container {#adr-002}

**Kontext.** Der Altstand schob Extraktionsjobs über ARQ/Redis an einen
separaten Worker-Container. Redis diente außerdem für Rate-Limits und einen
Log-Ring. Gemessen: fehlendes Redis machte die Suite 12× langsamer (262 s statt
22 s), weil jeder Zugriff in Retry-Timeouts lief — dokumentiert war das als
„best-effort-Degradation“.

**Entscheidung.** Eine `jobs`-Tabelle in SQLite plus ein asyncio-Task im
API-Prozess. Redis, ARQ und der Worker-Container entfallen.

**Warum.** Die Queue muss ein paar Jobs pro Tag verkraften, nicht Tausende pro
Sekunde. Eine Tabelle leistet das und bringt zwei Dinge mitgeschenkt, die die
Redis-Variante nicht hatte: Jobs sind **persistent** (ein Neustart verliert
keinen Auftrag) und **inspizierbar** (`SELECT * FROM jobs`).

**Konsequenzen.**
- Der Worker teilt den Prozess mit der API. Eine lange Extraktion blockiert
  nichts, weil sie `await`-basiert ist; die CPU-Last liegt beim LLM, nicht bei
  uns.
- Beim Start werden in `running` hängende Jobs requeued — Crash-Recovery, die
  es vorher nicht gab.
- Upload weckt den Worker über ein `asyncio.Event`, es gibt also keinen
  Poll-Delay.
- Rate-Limits sind jetzt prozesslokal (ein Prozess — identische Wirkung).
- Logs gehen nach stdout, also in `docker logs`. Die Admin-Log-Ansicht entfällt;
  der Fehlertext einer Extraktion steht am Bon, wo man ihn sucht.

**Zurücknehmen.** `services/jobs.py` ist die einzige Schnittstelle. Wer echte
Queue-Semantik braucht, ersetzt sie und lässt den Rest unberührt.

---

## ADR-003 — Geld als ganzzahlige Cent, Menge als Tausendstel {#adr-003}

**Kontext.** Der Altstand nutzte `Numeric`/`Decimal` in der DB und
serialisierte Beträge als JSON-**Strings**. Jede Frontend-Datei parste selbst
zurück; `pages/index.vue` brachte eigene `num()`/`eur()`-Helfer mit, obwohl
`utils/format.ts` dieselben Funktionen exportierte.

**Entscheidung.** Beträge sind überall `int` in Cent, benannt `*_cents`. Mengen
sind `int` in Tausendstel, benannt `quantity_milli`. Formatierung ausschließlich
über `formatCents()` im Frontend.

**Warum.** Der Rundungsfehler entsteht nicht in der Datenbank, sondern beim
Wiedereintritt an der UI-Grenze — genau dort, wo `parseFloat` stand. Integer
haben diese Grenze nicht: JSON kennt Ganzzahlen exakt, und `Number` hält Cent
bis 2^53 exakt. `Decimal` löst dasselbe Problem, aber nur solange niemand
`parseFloat` schreibt; Integer machen den Fehler unmöglich statt unwahrscheinlich.
Tausendstel für Mengen, weil `0,432 kg` exakt sein soll und
`sum()` über Floats sonst `1.2000000000000002` liefert.

**Konsequenzen.**
- Ein Feldnamen-Suffix (`_cents`, `_milli`) macht die Einheit an jeder
  Verwendungsstelle sichtbar — auch im Frontend-Typ.
- Division (Ø-Stückpreis, Budgetanteil) rundet explizit; das passiert
  ausschließlich in `domain/money.py`.
- Anteile gehen als Basispunkte (`share_bp`, 1/10.000) über die API, nicht als
  Fließkommazahl.

---

## ADR-004 — Ein Passwort statt Identitätssystem {#adr-004}

**Kontext.** `docs/anforderungen.md` des Altstands nannte Mehrbenutzerbetrieb
ausdrücklich als **Nicht-Ziel**. Implementiert waren dennoch Gruppen,
Mitgliedschaften, Rollen, Einladungen per Mail, OIDC-Client, Magic-Links mit
Browser-Bindung und Pairing-Codes sowie Refresh-Token-Familien mit
Reuse-Detection: rund 1.500 der 4.790 Backend-Zeilen.

**Entscheidung.** `AUTH_MODE` mit drei Werten:

| Modus | Verhalten |
| --- | --- |
| `password` (Default) | Ein Passwort aus `AUTH_PASSWORD`. Login setzt ein HMAC-signiertes, httpOnly-Session-Cookie. |
| `trusted_header` | Kein eigener Login. Ein Reverse Proxy (Authelia, Traefik Forward-Auth, authentik) authentifiziert und setzt `AUTH_TRUSTED_HEADER`. |
| `none` | Kein Auth. Nur für rein lokale Nutzung. |

Dazu API-Tokens (`edb_`-Präfix, nur als SHA-256-Hash gespeichert, einmalig im
Klartext gezeigt) für den iOS-Kurzbefehl.

**Warum.** Ein Nutzer braucht keine Identitätsverwaltung, sondern einen
Türriegel. `trusted_header` deckt den SSO-Wunsch in ~20 Zeilen ab, statt mit
einem eigenen OIDC-Client — und ist die im Homelab übliche Bauform, weil der
Proxy die Authentifizierung ohnehin schon macht.

**Konsequenzen.**
- Es gibt keine `users`-Tabelle. Kein Passwort-Reset, kein SMTP.
- `trusted_header` ist **nur** hinter einem Proxy sicher, der den Header
  überschreibt. Das steht als Warnung in `.env.example` und im README.
- Login ist prozesslokal rate-limitiert; das Passwort wird per
  `hmac.compare_digest` in konstanter Zeit verglichen.

**Zurücknehmen.** `api/deps.py` ist die einzige Stelle, an der eine Identität
entsteht. Wer Mehrbenutzerbetrieb will, fängt dort an — braucht dann aber
zusätzlich eine Mandantenspalte an `receipts` und `items`.

---

## ADR-005 — Vite + Vue statt Nuxt {#adr-005}

**Kontext.** Der Altstand nutzte Nuxt 3 mit `ssr: false`: kein SSR, keine
Server-Routes, kein Nitro — der volle Nuxt-Stack für eine SPA, die anschließend
ein separater nginx-Container auslieferte.

**Entscheidung.** Vite + Vue 3 + TypeScript + vue-router + Pinia + Tailwind v4
+ `vite-plugin-pwa`. Ausgeliefert wird das Build-Ergebnis von FastAPI selbst.

**Warum.** Von Nuxt blieben faktisch nur Datei-Routing und Auto-Imports übrig.
Für elf Seiten ist eine explizite Router-Tabelle *lesbarer* als Datei-Magie, und
explizite Imports machen sichtbar, woher `useResource` kommt. Nebeneffekt: der
nginx-Container entfällt, weil FastAPI die statischen Dateien mitausliefert
([ADR-006](#adr-006)).

**Konsequenzen.**
- Routen stehen explizit in `router.ts`.
- Alle Imports sind explizit — mehr Zeilen, dafür auffindbar.
- Kein SSR. War vorher auch nicht da.

---

## ADR-006 — Ein Container liefert API und SPA {#adr-006}

**Kontext.** `docker-compose.yml` des Altstands hatte neun Dienste: `db`,
`redis`, `migrate`, `backend`, `worker`, `frontend` (nginx),
`docker-socket-proxy`, `deploy-webhook` — plus 107 Zeilen `deploy.sh` mit
HMAC-Verifikation, Replay-Schutz und Auto-Rollback.

**Entscheidung.** Ein Multi-Stage-Dockerfile: Stage 1 baut die SPA, Stage 2
ist eine Python-Runtime, die die API bedient und das Build-Ergebnis als
statische Dateien ausliefert (mit SPA-Fallback auf `index.html`). Migrationen
laufen beim Start. `docker-compose.yml` hat einen Service und ein Volume.

**Warum.** Jeder Dienst ist ein eigener Fehlermodus, und keiner der acht
Zusatzdienste trug zur Kernfunktion bei. Ein Container heißt: ein Log, ein
Healthcheck, ein Neustart, kein CORS, kein Proxy-Pass, keine Reihenfolge beim
Hochfahren. Deploy ist `docker compose pull && docker compose up -d`.

**Konsequenzen.**
- API und Frontend sind versionsgleich — ein Schema-Mismatch zwischen zwei
  Images ist nicht möglich.
- Statische Dateien liefert Starlettes `StaticFiles` aus. Ausreichend für einen
  Haushalt; TLS und Kompression macht der Proxy davor.
- Routing-Reihenfolge ist relevant: `/api/*` zuerst, dann der SPA-Fallback.
  Steht als Kommentar an der Stelle.
- Migration beim Start ist bei SQLite unkritisch (ein Prozess, eine Datei).

---

## ADR-007 — `is_food` als Spalte statt Namensliste {#adr-007}

**Kontext.** `domain/aggregation.py` entschied über ein
`NON_FOOD_CATEGORIES`-Frozenset aus Kategorienamen, was Lebensmittel sind —
während die Kategorienverwaltung das Umbenennen erlaubte. Wer „Drogerie &
Körperpflege“ umbenannte, zählte sie stillschweigend zum Lebensmittelbudget.

**Entscheidung.** `categories.is_food` ist eine Boolean-Spalte, im UI
umschaltbar. Die Aggregation bekommt das Flag am Record.

**Warum.** Ein stiller Rechenfehler ist die schlechteste Fehlerart: die Zahl
sieht plausibel aus. Ein Datenfeld kann nicht durch eine Umbenennung
auseinanderlaufen.

**Konsequenzen.** Der Seed setzt das Flag; Unterkategorien erben es bei der
Anlage vom Elternteil als Vorschlag.

---

## ADR-008 — Ganzzahlige Primärschlüssel statt UUIDv7 {#adr-008}

**Kontext.** Der Altstand nutzte UUIDv7 (via `uuid6`-Abhängigkeit) für
zeitliche Sortierbarkeit.

**Entscheidung.** `INTEGER PRIMARY KEY` (SQLite-rowid).

**Warum.** UUIDs zahlen sich bei verteilter Erzeugung oder erratbaren URLs aus
— beides trifft nicht zu: ein Prozess erzeugt alle IDs, und alles liegt hinter
Auth. In SQLite ist die rowid zusätzlich der Cluster-Index, also die schnellste
und kleinste Variante. Zeitliche Sortierung liefert `created_at` explizit, was
lesbarer ist als eine implizite ID-Eigenschaft. Eine Abhängigkeit weniger.

**Konsequenzen.** IDs in URLs sind fortlaufend. Bei einem Single-User-System
hinter Auth ohne Belang. Dateinamen im Upload-Verzeichnis bleiben zufällig
(`secrets.token_hex`), damit der Dateipfad nicht erratbar ist.

---

## ADR-009 — Charts selbst schreiben {#adr-009}

**Kontext.** Gebraucht werden vier Darstellungen: Donut (Kategorienanteile),
Linie (Preisverlauf), Ranking-Balken, Sparkline.

**Entscheidung.** Handgeschriebenes SVG in `charts/`, keine Chart-Bibliothek.

**Warum.** Chart.js oder ECharts kosten 60–150 kB für vier Diagrammtypen und
bringen ihr eigenes Theming mit, das sich mit den Design-Tokens streiten würde.
Die vier Typen sind zusammen ~400 Zeilen SVG, nutzen dieselben CSS-Variablen wie
der Rest der App und funktionieren im Dark Mode automatisch mit.

**Konsequenzen.** Achsen, Ticks und Hover sind selbst gebaut. Wer später
Zoom oder Brushing braucht, sollte auf eine Bibliothek wechseln — die
Chart-Komponenten sind austauschbar hinter ihrer Props-Schnittstelle.

---

## ADR-010 — Tests ohne Infrastruktur {#adr-010}

**Kontext.** Die alte Suite brauchte Postgres **und** Redis, löschte per
`autouse`-Fixture vor jedem Test drei Tabellen und seedete den Kategorienbaum
neu; `app_client` baute pro Test die App inklusive Lifespan auf. Laufzeit 22 s
mit Redis, 262 s ohne — und `make check` scheiterte auf dem dokumentierten
Setup an einem Port-Widerspruch.

**Entscheidung.** Jeder Test läuft gegen eine temporäre SQLite-Datei pro
Test-Session; die App wird einmal gebaut. Kein externer Dienst, keine
Portannahme, kein `.env`-Einfluss. Der LLM-Adapter wird über einen Fake
injiziert.

**Warum.** Eine Suite, die Infrastruktur braucht, wird umgangen. Nach dem
Wegfall von Postgres und Redis ist die Alternative geschenkt.

**Konsequenzen.** Dialektspezifische Fehler würde diese Suite nicht finden —
belanglos, weil SQLite auch produktiv läuft. Die Fixtures liegen in
`tests/conftest.py`, Umgebungsvariablen werden dort explizit gesetzt statt
`setdefault` (der Fehler, der zum Port-Widerspruch führte).
