# Konzept

Quelle der Wahrheit für das *Was* und *Warum*. Scope-Änderungen hier pflegen.

## Der Satz, auf den sich alles reduziert

> **Bon abfotografieren → sehen, wo das Geld hingeht und was teurer wird.**

Ein Haushalt, ein Server, ein Container. Alles, was diesem Satz nicht dient,
ist raus.

## Leitprinzipien

1. **Die Analyse ist das Produkt, der Scan ist Zulieferung.** Wo Aufwand
   investiert wird, entscheidet dieser Satz. Der Scan muss zuverlässig sein,
   die Analyse muss *gut aussehen und Erkenntnisse liefern*.
2. **Betriebsgröße ernst nehmen.** Ein Haushalt, ein Nutzer, ~50 Bons im Monat.
   Das ist keine verteilte Anwendung. Ein Prozess, eine Datei, ein Container.
3. **Ein Fehler darf niemals eine Seite leeren.** Jedes Widget lädt und scheitert
   für sich.
4. **Geld ist nie eine Fließkommazahl und nie ein String.** Ganzzahlige Cent
   von der Datenbank bis ins Template, eine einzige Formatierungsfunktion.
5. **Mobil ist der Standardfall.** Der Bon wird an der Kasse fotografiert, nicht
   am Schreibtisch hochgeladen.
6. **Ohne konfiguriertes LLM voll bedienbar.** Kein Modell = eBon-Parser plus
   manuelle Erfassung. Die App ist nie unbenutzbar.

## Funktionaler Scope

### Erfassen
- Upload von Bild (JPEG/PNG/WebP/HEIC) oder PDF — per Kamera, Drag & Drop,
  Dateiauswahl oder Mehrfachauswahl.
- Typprüfung über Magic Bytes, nicht über den Client-Content-Type.
- Extraktion läuft asynchron; die UI zeigt den Status live (Polling).
- Statusfluss: `uploaded → processing → done | needs_review | failed`.
- Zwei Extraktionswege: **Text-PDF-Parser** (eBons, ohne Modell) und
  **Vision-LLM** (Fotos, Scans). Bei Zweifel `needs_review` statt Absturz.
- Headless-Upload per API-Token (iOS-Kurzbefehl aus dem Teilen-Menü).

### Korrigieren
- Bon-Detailseite: Kopfdaten und Positionen editierbar, Originalbeleg daneben.
- Position anlegen, ändern, löschen; Kategorie zuweisen; als geprüft markieren.
- Korrigierte Namen laufen serverseitig durch dieselbe Normalisierung wie
  extrahierte — eine Korrektur landet am selben Trend-Anker.
- Neu-Extraktion eines Bons auf Knopfdruck.

### Auswerten (das Herzstück)
- **Monat:** Gesamtausgaben, Produkt-/Pfand-/Rabattanteil, Bon-Anzahl,
  Aufschlüsselung nach Kategorie und Markt, teuerste Einzelpositionen.
- **Artikel-Ranking** in drei Sortierungen: Häufigkeit („kaufe ich zu oft“),
  Gesamtausgabe („teure Lebensmittel“), Durchschnitts-Stückpreis.
- **Anteil am Lebensmittelbudget** je Artikel.
- **Preisverlauf pro Artikel** über beliebig viele Monate.
- **Vormonatsvergleich** gesamt und je Kategorie.

### Verwalten
- Kategorien hierarchisch anlegen, umbenennen, umhängen, löschen.
- `is_food` ist ein **Feld** an der Kategorie, keine Namensliste im Code.
- API-Tokens anlegen und widerrufen.

## Nicht-Ziele (bewusst und begründet)

| Nicht-Ziel | Begründung |
| --- | --- |
| Mehrbenutzer, Gruppen, Einladungen, Rollen | Ein Haushalt. War im Altstand ein Drittel des Backends für ein Feature, das die Anforderungen ausdrücklich ausschließen. |
| OIDC-Client, Magic-Links, SMTP | Ein Nutzer braucht kein Identitätssystem. Wer SSO will, stellt Authelia als Forward-Auth davor — dafür gibt es `AUTH_MODE=trusted_header` (siehe [ADR-004](entscheidungen.md#adr-004)). |
| Redis, ARQ, separater Worker | Bei ~50 Bons/Monat reicht eine DB-gestützte Queue im selben Prozess ([ADR-002](entscheidungen.md#adr-002)). |
| Postgres | Ein Schreiber, wenige MB Daten. SQLite im WAL-Modus ist hier die robustere Wahl, weil Backup = eine Datei kopieren ([ADR-001](entscheidungen.md#adr-001)). |
| Deploy-Webhook, docker-socket-proxy | 300 Zeilen Infrastruktur, die `docker compose pull && up -d` ersetzen. Nicht das Problem dieser App. |
| Echtzeit-Transport (WebSocket) | Polling genügt für einen Statuswechsel, der Sekunden dauert. |
| Bestell-/Lieferdienste, Essensplanung, MCP | Nicht Teil des Satzes oben. |

## Was der Nutzer nach dem Neuschnitt merkt

| Vorher | Nachher |
| --- | --- |
| 9 Container, Postgres + Redis + nginx + Webhook | **1 Container**, eine SQLite-Datei |
| Tests brauchen Postgres **und** Redis, 22–262 s | Tests brauchen **nichts**, wenige Sekunden |
| `make check` scheitert auf dem dokumentierten Setup | `make check` läuft nach `make install` |
| 768-px-Spalte, 7 umbrechende Text-Links | Sidebar auf Desktop, Bottom-Nav + Kamera-FAB auf Mobil |
| Nacktes `<input type="file">` | Kamera, Drag & Drop, Vorschau, Mehrfach-Queue mit Live-Status |
| Ein fehlgeschlagener Request = weiße Seite | Jedes Widget lädt und scheitert einzeln |
| Kein Dark Mode, „Lädt …“ als Ladezustand | Dark Mode, Skeletons, Toasts |
| Geld als String, pro Datei neu geparst | Ganzzahlige Cent, eine Formatierungsfunktion |
| 2 Komponenten, ~30× dieselbe Utility-Kette | Design-System mit Tokens, Primitives und 4 Chart-Typen |
