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

## ADR-004 — Vier Anmeldemodi, Haushalt als Mandantengrenze {#adr-004}

**Kontext.** `docs/anforderungen.md` des Altstands nannte Mehrbenutzerbetrieb
ausdrücklich als **Nicht-Ziel**. Implementiert waren dennoch Gruppen,
Mitgliedschaften, Rollen, Einladungen per Mail, OIDC-Client, Magic-Links mit
Browser-Bindung und Pairing-Codes sowie Refresh-Token-Familien mit
Reuse-Detection: rund 1.500 der 4.790 Backend-Zeilen.

Der erste Schnitt dieses Umbaus hat das alles gestrichen und nur `password`,
`trusted_header` und `none` behalten. Diese Fassung ist die Revision danach: der
Mehrbenutzerbetrieb ist gewollt — getrennte Daten pro Haushalt, Einladungen,
OIDC — die *teuren* Teile des Altstands bleiben aber draußen.

**Entscheidung.** Zwei getrennte Achsen: **wer bist du** (`AUTH_MODE`) und
**welche Daten siehst du** (aktiver Haushalt).

| Modus | Verhalten | Mehrere Menschen? |
| --- | --- | --- |
| `password` (Default) | Ein Passwort aus `AUTH_PASSWORD`. Login setzt ein HMAC-signiertes, httpOnly-Session-Cookie und meldet immer denselben technischen Nutzer an. | nein |
| `oidc` | Authorization-Code-Flow gegen einen Identity Provider (Discovery, `state`-Cookie, `userinfo`). | ja |
| `trusted_header` | Kein eigener Login. Ein Reverse Proxy (Authelia, Traefik Forward-Auth, authentik) authentifiziert und setzt `AUTH_TRUSTED_HEADER`. | ja |
| `none` | Kein Auth. Nur für rein lokale Nutzung. | nein |

Dazu API-Tokens (`edb_`-Präfix, nur als SHA-256-Hash gespeichert, einmalig im
Klartext gezeigt) für den iOS-Kurzbefehl.

Der **Haushalt** ist die Mandantengrenze: `receipts` und `items` tragen
`household_id NOT NULL`, jede Abfrage filtert danach. Rollen gibt es zwei,
`admin` und `member` — mehr wäre für „wer darf einladen und umbenennen“ nicht
nötig. Auch `password` und `none` bekommen genau einen Haushalt, damit die
Mandantenprüfung überall dieselbe ist und nicht als Sonderfall existiert.

Was **nicht** zurückkommt: Magic-Links mit Browser-Bindung, Pairing-Codes,
Refresh-Token-Familien mit Reuse-Detection, eigene Passwortverwaltung. Es gibt
deshalb keine Passwortspalte an `users`; eine Identität entsteht über OIDC, über
den Proxy-Header oder als technischer Einzelnutzer.

**Warum.** Getrennte Haushalte sind eine Datenmodell-Frage, keine
Protokoll-Frage — der teure Teil des Altstands war die selbstgebaute
Anmeldung, nicht die Mandantentrennung. Die Anmeldung selbst delegieren wir
darum: an einen Identity Provider (`oidc`) oder an den Proxy
(`trusted_header`), der im Homelab ohnehin davor steht. Beim OIDC-Client ist
`subject` der Anker, nicht die Mailadresse — die darf beim Provider wechseln,
ohne dass jemand seinen Haushalt verliert.

Der aktive Haushalt kommt aus dem Header `X-Household-Id`, sonst aus dem Cookie
`eb_household`, sonst ist es die älteste Mitgliedschaft. Der Header gewinnt,
weil nur er synchron ist: sonst träfe die Anfrage direkt nach dem Klick noch den
alten Haushalt.

**Konsequenzen.**
- Der Rollencheck hängt an einer Dependency-Kette
  (`require_user` → `require_household` → `require_household_admin`) und nicht in
  jedem Handler.
- Fremde IDs antworten mit **404**, nicht 403 — die API verrät nicht, welche IDs
  es gibt. Ausnahme: der Wechsel in einen fremden Haushalt gibt 403, denn dass
  der Haushalt existiert, weiß der Aufrufer dort schon.
- `trusted_header` ist **nur** hinter einem Proxy sicher, der den Header
  überschreibt. Das steht als Warnung in `.env.example` und im README.
- Login ist prozesslokal rate-limitiert; Passwort und `state` werden per
  `hmac.compare_digest` in konstanter Zeit verglichen.
- Einladungen und weitere Haushalte sind in `password`/`none` abgeschaltet — in
  einem Modus, in dem sich ein zweiter Mensch nicht anmelden kann, wäre eine
  Einladung eine Sackgasse.
- Der letzte Admin eines Haushalts kann sich nicht selbst herabstufen oder
  entfernen; sonst bliebe ein Haushalt ohne Verwaltung zurück.

**Zurücknehmen.** `api/deps.py` ist die einzige Stelle, an der eine Identität
und ein aktiver Haushalt entstehen. Wer zurück auf Einzelbetrieb will, setzt
`AUTH_MODE=password`: Haushalte, Einladungen und die OIDC-Routen bleiben dann
ungenutzt im Code, ohne dass etwas ausgebaut werden muss.

---

## ADR-005 — Vite + Vue statt Nuxt {#adr-005}

**Kontext.** Der Altstand nutzte Nuxt 3 mit `ssr: false`: kein SSR, keine
Server-Routes, kein Nitro — der volle Nuxt-Stack für eine SPA, die anschließend
ein separater nginx-Container auslieferte.

**Entscheidung.** Vite + Vue 3 + TypeScript + vue-router + `vite-plugin-pwa`.
Ausgeliefert wird das Build-Ergebnis von FastAPI selbst. (Tailwind und Pinia
fallen ebenfalls weg — siehe [ADR-011](#adr-011).)

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

---

## ADR-011 — Design-System aus Tokens statt Utility-Klassen {#adr-011}

**Kontext.** Der Altstand nutzte Tailwind ohne Design-Ebene darüber:
`rounded border bg-white p-4` stand rund 30× wortgleich im Code, Farben wie
`bg-green-600` und `text-gray-500` waren über elf Seiten verstreut, `main.css`
enthielt genau eine Zeile. Es gab zwei Komponenten für elf Seiten, keinen Dark
Mode und keine Skeletons.

**Entscheidung.** Kein Tailwind, kein Pinia. Statt dessen:

1. `styles/tokens.css` — die **einzige** Datei mit Farbwerten, je für Light und
   Dark.
2. `ui/` — Primitives (Button, Card, Badge, Input, Select, MoneyInput, Modal,
   Skeleton, Empty, Toast, Stat, Segmented, Icon).
3. Alles Weitere in `<style scoped>` der jeweiligen Komponente.
4. Zustand in Modulen mit `ref`s statt in einem Store-Framework.

**Warum.** Die Duplikation im Altstand entstand nicht durch Tailwind, sondern
durch die fehlende Ebene darüber — Seiten wurden vor den Bausteinen gebaut.
Diese Reihenfolge umzudrehen ist die eigentliche Korrektur; Tailwind wird danach
nicht mehr gebraucht, weil jede Komponente ihre Stile ohnehin selbst besitzt.
Nebeneffekte: „kein Hex-Wert außerhalb von `tokens.css`“ ist eine prüfbare
Regel, der Dark Mode entsteht aus derselben Quelle statt aus `dark:`-Varianten an
jeder Klasse, und eine Build-Abhängigkeit fällt weg. Pinia entfällt, weil es zwei
Zustände gibt (Session, Kategorien) und keiner Zeitreise oder SSR-Isolierung
braucht.

**Konsequenzen.**
- Scoped CSS ist etwas mehr Text als eine Utility-Kette, aber lokal und benannt.
- Wer ein neues Element baut, greift zuerst in `ui/` — fehlt dort etwas, gehört
  es dort hinein und nicht in die Seite.
- Ohne Utility-Klassen gibt es keinen „Notausgang“ für Einzelfälle; einige
  Layout-Helfer (`stack`, `row`, `grid-cards`, `num`, `truncate`) stehen deshalb
  global in `base.css`.

**Zurücknehmen.** Tailwind ließe sich zusätzlich einführen, ohne die Primitives
anzutasten — die Tokens wären dann seine Theme-Quelle.

---

## ADR-012 — Kategorien bleiben global, Artikel werden pro Haushalt getrennt {#adr-012}

**Kontext.** Mit dem Haushalt als Mandantengrenze ([ADR-004](#adr-004)) muss für
jede Tabelle entschieden werden, ob sie geteilt wird oder nicht. Bei `receipts`
und `line_items` ist die Antwort offensichtlich. Bei den beiden Stammdatentabellen
`categories` und `items` nicht.

**Entscheidung.**

- `categories` bleibt **global**, ohne `household_id`.
- `items` wird **pro Haushalt** getrennt, mit
  `UNIQUE (household_id, normalized_name)`.

**Warum.** Die beiden Tabellen beantworten verschiedene Fragen. „Joghurt & Quark“
ist überall dasselbe — die Kategorien kommen aus dem Seed, sie sind Vokabular,
kein Nutzerinhalt. Sie zu vervielfachen brächte identische Zeilen pro Haushalt
und den Zwang, den Seed bei jedem neuen Haushalt zu wiederholen.

`items` dagegen **ist** Nutzerinhalt: an einem Artikel hängt der Preisverlauf.
Wären Artikel global, würden zwei Haushalte, die beide „H-Milch 3,5 %“ kaufen,
sich eine Preiskurve teilen — und damit gegenseitig ihre Einkaufspreise
offenlegen. Das ist genau das Leck, das die Mandantentrennung verhindern soll;
`test_tenancy.py::test_same_product_becomes_two_items` prüft es.

**Konsequenzen.**
- Wer eine Kategorie umbenennt, benennt sie für alle Haushalte um. Bei einem
  gemeinsam genutzten Vokabular ist das erwartbar, es steht als Hinweis auf der
  Kategorienseite.
- Derselbe Artikelname existiert n-mal in `items` — n = Zahl der Haushalte, die
  ihn gekauft haben. Bei den Datenmengen dieser App belanglos.
- Die Auswertungen joinen `items` immer über `household_id` mit; ein vergessener
  Join fällt in den Mandantentests auf, nicht erst im Betrieb.

**Zurücknehmen.** Kategorien pro Haushalt wären eine Migration (Spalte, Backfill
je Haushalt, `UNIQUE` erweitern) plus der Seed an der Stelle, an der ein Haushalt
entsteht (`services/users.py`). Der umgekehrte Weg — Artikel global — ist
bewusst keine Option.

---

## ADR-013 — Einladung per Token-Link, Beitritt nach der Anmeldung {#adr-013}

**Kontext.** Jemanden in einen Haushalt holen heißt: eine Person, die die App
noch nicht kennt, muss sich anmelden **und** dem richtigen Haushalt zugeordnet
werden. Der Altstand löste das mit Magic-Links samt Browser-Bindung und
Pairing-Codes — der aufwendigste Teil des alten Auth-Codes.

**Entscheidung.** Eine Einladung ist eine Zeile in `invitations` mit Mailadresse,
Rolle, Ablaufdatum und einem Zufallstoken. Der Link
(`/einladung?token=…`) geht per Mail hinaus; ist kein `SMTP_HOST` gesetzt,
liefert die API den Link in der Antwort zurück und schreibt ihn ins Log.
Eingelöst wird er von einem **angemeldeten** Nutzer: erst Anmeldung
(OIDC/Proxy), dann Beitritt.

**Warum.** Die Reihenfolge „anmelden, dann beitreten“ macht den Link zu einem
reinen Berechtigungsnachweis und nicht zu einem zweiten Anmeldeverfahren. Damit
entfällt der ganze Magic-Link-Apparat. Sie löst außerdem ein praktisches Problem:
der Identity Provider liefert nicht zwangsläufig dieselbe Mailadresse, an die
eingeladen wurde — der Token ist die Autorisierung, die Adresse nur die
Zustelladresse.

Der Mailversand läuft über `smtplib` aus der Standardbibliothek in einem Thread.
Für eine Mail pro Einladung braucht es keine Mail-Bibliothek.

**Konsequenzen.**
- Wer den Link hat, kann beitreten. Er ist kurzlebig
  (`INVITATION_TTL_HOURS`, Standard 168) und zurückziehbar.
- Ohne SMTP verschwindet keine Einladung spurlos — die Oberfläche zeigt den Link
  zum Weitergeben und sagt, dass keine Mail verschickt wurde.
- Ein fehlgeschlagener Mailversand lässt die Einladung stehen; sie ist bereits in
  der Datenbank, wenn die Mail rausgeht.

**Zurücknehmen.** Die Einladung ist auf `services/households.py` und eine
Tabelle begrenzt. Wer stattdessen Provider-Gruppen abbilden will, ersetzt
`accept_invitation` durch eine Zuordnung aus dem OIDC-Claim.

---

## ADR-014 — OIDC ohne JWKS: Code-Flow plus `userinfo` {#adr-014}

**Kontext.** Ein OIDC-Client kann die Identität auf zwei Wegen bekommen: das
`id_token` selbst prüfen (Signatur über JWKS, Schlüsselrotation, Clock Skew,
`aud`/`iss`/`nonce`-Prüfung) oder den Access-Token gegen den
`userinfo`-Endpoint einlösen.

**Entscheidung.** Confidential Client mit Authorization-Code-Flow über
`httpx`; die Identität kommt aus `userinfo`. Das `id_token` wird nicht
kryptografisch geprüft. Discovery
(`/.well-known/openid-configuration`) wird pro Prozess einmal geholt und
gecacht. `state` liegt in einem kurzlebigen httpOnly-Cookie und wird im Callback
in konstanter Zeit verglichen.

**Warum.** Der Token-Tausch läuft über TLS direkt gegen den Provider, mit
Client-Secret — der Kanal ist authentifiziert, und `userinfo` liefert dieselbe
Identität. Die JWKS-Variante würde `python-jose`/`authlib` samt
Krypto-Abhängigkeit und Schlüsselrotation dazuholen, um denselben Anker
(`subject`) zu bekommen. Für eine Selbsthosting-App ist das Aufwand ohne
Sicherheitsgewinn.

**Konsequenzen.**
- Ein zusätzlicher HTTP-Aufruf pro Anmeldung (`userinfo`). Bei einer Anmeldung
  pro Sitzung irrelevant.
- Kein `nonce`-Replay-Schutz auf dem `id_token` — der wird nicht ausgewertet.
  Gegen untergeschobene Callbacks schützt der `state`-Vergleich.
- Fehler des Providers landen als Umleitung auf `/login?sso_error=…`; ein Browser
  sieht nie eine JSON-Fehlerseite.
- `OIDC_ISSUER`, `OIDC_CLIENT_ID` und `OIDC_CLIENT_SECRET` sind Pflicht, sonst
  antwortet `/api/auth/oidc/login` mit 503 statt einer halben Umleitung.

**Zurücknehmen.** `integrations/oidc.py` ist die einzige Stelle mit
Provider-Wissen und über `set_oidc_client()` austauschbar — die Tests nutzen
genau diesen Haken. Wer das `id_token` prüfen will, ersetzt `exchange()`.
