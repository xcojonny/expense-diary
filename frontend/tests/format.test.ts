import { describe, expect, it } from 'vitest'

import {
  formatDate,
  formatDateShort,
  fromDateInput,
  monthLabel,
  monthName,
  pluralize,
  relativeTime,
  toDateInput,
} from '@/lib/format'

describe('Monatsnamen', () => {
  it('benennt Monate deutsch', () => {
    expect(monthName(1)).toBe('Januar')
    expect(monthName(12)).toBe('Dezember')
    expect(monthLabel(2026, 3)).toBe('März 2026')
  })

  it('bleibt bei ungültigem Monat brauchbar', () => {
    expect(monthName(13)).toBe('13')
  })
})

describe('Datumsformate', () => {
  it('formatiert ISO-Zeitstempel', () => {
    expect(formatDate('2026-03-04T17:42:00')).toBe('04.03.2026')
    expect(formatDateShort('2026-03-04T17:42:00')).toBe('04.03.')
  })

  it('zeigt einen Platzhalter für fehlende oder kaputte Werte', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('')).toBe('—')
    expect(formatDate('kein datum')).toBe('—')
  })
})

describe('Datumsfelder', () => {
  it('geht ohne Zeitzonen-Verschiebung hin und zurück', () => {
    // Der Fehler, den das verhindert: ein Einkauf am 1. rutscht durch eine
    // UTC-Konvertierung auf den Vortag im Vormonat.
    const iso = '2026-03-01T00:00:00'
    const forField = toDateInput(iso)
    expect(forField).toBe('2026-03-01')
    expect(fromDateInput(forField)).toBe('2026-03-01T00:00:00')
  })

  it('behandelt Leerwerte', () => {
    expect(toDateInput(null)).toBe('')
    expect(fromDateInput('')).toBeNull()
  })
})

describe('relativeTime', () => {
  it('beschreibt kurze Abstände', () => {
    expect(relativeTime(new Date().toISOString())).toBe('gerade eben')
    expect(relativeTime(new Date(Date.now() - 5 * 60_000).toISOString())).toBe('vor 5 min')
    expect(relativeTime(new Date(Date.now() - 3 * 3_600_000).toISOString())).toBe('vor 3 h')
  })

  it('fällt bei alten Werten auf das Datum zurück', () => {
    expect(relativeTime('2020-01-15T10:00:00')).toBe('15.01.2020')
  })
})

describe('pluralize', () => {
  it('wählt Singular und Plural', () => {
    expect(pluralize(1, 'Bon', 'Bons')).toBe('1 Bon')
    expect(pluralize(0, 'Bon', 'Bons')).toBe('0 Bons')
    expect(pluralize(7, 'Bon', 'Bons')).toBe('7 Bons')
  })
})
