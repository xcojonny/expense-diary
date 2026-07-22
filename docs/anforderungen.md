# Anforderungen

Quelle der Wahrheit für das *Was*. Änderungen am Scope hier pflegen.

## Ziel

Eine self-hosted Web-App, in die Fotos/PDFs von Kassenbons hochgeladen werden.
Ein Vision-LLM extrahiert jede Position einzeln (Name, Menge, Preis, Kategorie).
Am Monatsende entsteht ein Bericht über **Ausgaben UND Sparpotenzial**: Welche
Lebensmittel sind teuer, was wird zu oft/zu viel gekauft, Preistrends pro Artikel
über die Zeit.

Der Mehrwert liegt in der **Analyse-Ebene**, nicht im Scan. Der Bon-Scan ist ein
gelöstes Standardproblem und wird bewusst schlank gehalten.

## Nicht-Ziele

- Kein Multi-User-/Gruppen-Modell (privates Homelab, ein Haushalt).
- Keine Bestell-/Lieferdienst-Anbindung, keine Essensplanung.
- Kein Echtzeit-Transport (kein WebSocket) — Live-Updates via Polling.

## Funktionale Anforderungen

### Erfassung & Extraktion
- Upload von Bild (JPEG/PNG/WebP) oder PDF eines Kassenbons.
- Extraktion läuft **asynchron**; das Frontend pollt den Verarbeitungsstatus
  (~alle 2 s) bis ein Endzustand erreicht ist.
- Status am Receipt: `uploaded → processing → done | needs_review | failed`.
- Das LLM erzwingt striktes JSON nach festem Schema (siehe
  `backend/app/prompts/receipt_extraction.de.txt`). Deutsche Bons als primärer
  Anwendungsfall.
- Bei Parsing-Problemen `needs_review` statt Absturz, damit manuell korrigiert
  werden kann.
- Der Extraktions-Prompt liegt in einer eigenen, leicht editierbaren Datei.

### Analyse-Ebene (das Herzstück)
- **Monatsbericht:** Gesamtausgaben, Aufschlüsselung nach Kategorie, Top-N
  teuerste Einzelpositionen, Ausgaben pro Store.
- **„Was kaufe ich zu viel":** Artikel nach Häufigkeit und Gesamtmenge im Monat.
- **„Teure Lebensmittel":** Artikel nach Gesamtausgabe und nach Stückpreis,
  inkl. Anteil am Lebensmittelbudget.
- **Preistrend pro Artikel:** `unit_price` über die Zeit (für Chart).
- **Vormonatsvergleich.**

### Verwaltung
- Dashboard: Bon-Liste + Detailansicht mit editierbaren Positionen.
- Kategorien-Verwaltung (hierarchisch) und manuelle Korrektur von Positionen.

## Nicht-funktionale Anforderungen

- Sauberes Adapter-Interface für das LLM (Protocol/ABC), damit ein Wechsel zu
  Ollama nur eine neue Implementierung ist. API-Key, Base-URL, Modellname als ENV.
- Tests für die Analyse-Aggregationen (die kritische Logik).
- README mit Setup-Schritten und benötigten ENV-Variablen.
- Self-hosted, docker-compose (db, backend, frontend), lauffähig ohne
  konfiguriertes LLM (`LLM_PROVIDER=none`).

## Reihenfolge / Prioritäten

1. Datenmodell + Migrations + docker-compose (lauffähiges Grundgerüst) — **erledigt**
2. Upload + Extraktions-Pipeline mit LLM-Adapter + Status-Polling
3. Dashboard (Bon-Liste, Detailansicht mit editierbaren Positionen)
4. Analyse-Endpoints + Report-Ansicht mit Charts
5. Kategorien-Verwaltung + manuelle Korrektur
