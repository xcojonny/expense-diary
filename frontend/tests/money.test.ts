/**
 * Geldformatierung und -eingabe.
 *
 * Die wichtigsten Tests im Frontend: hier entstand im Altstand der
 * Rundungsfehler, weil jede Seite Beträge selbst mit `parseFloat` zurückparste.
 */
import { describe, expect, it } from 'vitest'

import {
  bpToFraction,
  centsToInput,
  formatBp,
  formatBpSigned,
  formatCents,
  formatCentsRounded,
  formatQuantity,
  formatQuantityWithUnit,
  milliToInput,
  parseCentsInput,
  parseQuantityInput,
} from '@/lib/money'

/** Intl nutzt ein schmales geschütztes Leerzeichen (U+202F) vor dem €. */
const norm = (value: string) => value.replace(/\u00a0|\u202f/g, ' ')

describe('formatCents', () => {
  it('formatiert Cent als deutschen Betrag', () => {
    expect(norm(formatCents(109))).toBe('1,09 €')
    expect(norm(formatCents(0))).toBe('0,00 €')
    expect(norm(formatCents(-50))).toBe('-0,50 €')
    expect(norm(formatCents(123456))).toBe('1.234,56 €')
  })

  it('zeigt einen Platzhalter statt „NaN €"', () => {
    expect(formatCents(null)).toBe('—')
    expect(formatCents(undefined)).toBe('—')
    expect(formatCents(Number.NaN)).toBe('—')
  })

  it('rundet in der gerundeten Variante ohne Nachkomma', () => {
    expect(norm(formatCentsRounded(123456))).toBe('1.235 €')
  })
})

describe('parseCentsInput', () => {
  it.each([
    ['1,09', 109],
    ['1.09', 109],
    ['1', 100],
    ['0,05', 5],
    ['-0,50', -50],
    ['1.234,56', 123456],
    [' 2,00 € ', 200],
    ['3,5', 350],
    ['0', 0],
  ])('liest „%s" als %i Cent', (input, expected) => {
    expect(parseCentsInput(input)).toBe(expected)
  })

  it.each(['', '   ', 'abc', '1,2,3', '--1', '1,234,5'])('lehnt „%s" ab', (input) => {
    expect(parseCentsInput(input)).toBeNull()
  })

  it('rechnet mit Ganzzahlen — kein Fließkommafehler', () => {
    // 0,1 + 0,2 wäre in Fließkomma 0.30000000000000004.
    const sum = (parseCentsInput('0,10') ?? 0) + (parseCentsInput('0,20') ?? 0)
    expect(sum).toBe(30)
    expect(norm(formatCents(sum))).toBe('0,30 €')
  })

  it('ist die Umkehrung von centsToInput', () => {
    for (const cents of [0, 1, 99, 100, 109, 12345, -50]) {
      expect(parseCentsInput(centsToInput(cents))).toBe(cents)
    }
  })
})

describe('Mengen in Tausendstel', () => {
  it('formatiert und parst verlustfrei', () => {
    expect(formatQuantity(780)).toBe('0,78')
    expect(formatQuantity(2000)).toBe('2')
    expect(formatQuantity(1500)).toBe('1,5')
    expect(parseQuantityInput('0,78')).toBe(780)
    expect(parseQuantityInput('2')).toBe(2000)
    expect(parseQuantityInput('0,432')).toBe(432)
  })

  it('hängt die Einheit an', () => {
    expect(formatQuantityWithUnit(780, 'kg')).toBe('0,78 kg')
    expect(formatQuantityWithUnit(2000, null)).toBe('2')
    expect(formatQuantityWithUnit(null, 'kg')).toBe('—')
  })

  it('liefert für Eingabefelder einen leeren String statt eines Platzhalters', () => {
    expect(milliToInput(null)).toBe('')
    expect(milliToInput(780)).toBe('0,78')
  })

  it('summiert exakt — anders als Fließkomma-Mengen', () => {
    // 0,1 + 0,2 + 0,3 kg ergäbe als Float 0.6000000000000001.
    const total = [100, 200, 300].reduce((sum, value) => sum + value, 0)
    expect(formatQuantity(total)).toBe('0,6')
  })
})

describe('Basispunkte', () => {
  it('formatiert Anteile', () => {
    expect(formatBp(2500)).toBe('25 %')
    expect(formatBp(5220)).toBe('52,2 %')
    expect(formatBp(null)).toBe('—')
  })

  it('formatiert Veränderungen mit Vorzeichen', () => {
    expect(formatBpSigned(2000)).toBe('+20 %')
    expect(formatBpSigned(-1550)).toBe('-15,5 %')
    expect(formatBpSigned(null)).toBe('—')
  })

  it('begrenzt Balkenanteile auf 0..1', () => {
    expect(bpToFraction(2500)).toBe(0.25)
    expect(bpToFraction(20000)).toBe(1)
    expect(bpToFraction(-500)).toBe(0)
    expect(bpToFraction(null)).toBe(0)
  })
})
