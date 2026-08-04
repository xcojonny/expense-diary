/**
 * Geld und Mengen im Frontend — das Gegenstück zu `domain/money.py`.
 *
 * Die API liefert ganzzahlige Cent (ADR-003). Diese Datei ist die **einzige**
 * Stelle, die daraus Text macht. Im Altstand kamen Beträge als String und jede
 * Seite parste sie mit eigenem `parseFloat` zurück — genau das ist hier
 * unmöglich, weil es nichts zu parsen gibt.
 */

const EUR = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const EUR_ROUND = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const DECIMAL = new Intl.NumberFormat('de-DE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export const PLACEHOLDER = '—'

/** Cent als Betrag: `109` → `1,09 €`. */
export function formatCents(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return PLACEHOLDER
  return EUR.format(cents / 100)
}

/** Cent ohne Nachkomma — für große Kennzahlen: `123456` → `1.235 €`. */
export function formatCentsRounded(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return PLACEHOLDER
  return EUR_ROUND.format(cents / 100)
}

/** Cent als Zahl ohne Währung, für Eingabefelder: `109` → `1,09`. */
export function centsToInput(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return ''
  return DECIMAL.format(cents / 100)
}

/**
 * Eingabe zu Cent — mit Ganzzahl-Arithmetik, ohne `parseFloat`.
 *
 * Akzeptiert „1,09", „1.09", „1", „-0,50", „1.234,56", „3,5" und „ 2,00 € ".
 * `null` bei allem, was keine Zahl ist.
 */
export function parseCentsInput(raw: string): number | null {
  const cleaned = raw.trim().replace(/[\s\u00a0\u202f€]/g, '')
  if (!cleaned) return null

  // Tausenderpunkte entfernen ("1.234,56"), aber "1.09" als Dezimalpunkt lassen.
  const normalized = cleaned.includes(',')
    ? cleaned.replace(/\./g, '').replace(',', '.')
    : cleaned

  const match = /^(-?)(\d*)(?:\.(\d{1,2}))?$/.exec(normalized)
  if (!match || (!match[2] && !match[3])) return null

  const sign = match[1] === '-' ? -1 : 1
  const euros = match[2] ? Number.parseInt(match[2], 10) : 0
  const fraction = (match[3] ?? '').padEnd(2, '0')
  return sign * (euros * 100 + Number.parseInt(fraction, 10))
}

/** Tausendstel als Menge: `780` → `0,78`, `2000` → `2`. */
export function formatQuantity(milli: number | null | undefined): string {
  if (milli === null || milli === undefined || !Number.isFinite(milli)) return PLACEHOLDER
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 3 }).format(milli / 1000)
}

/** Menge mit Einheit: `780`, `"kg"` → `0,78 kg`. */
export function formatQuantityWithUnit(
  milli: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (milli === null || milli === undefined) return PLACEHOLDER
  const value = formatQuantity(milli)
  return unit ? `${value} ${unit}` : value
}

/** Tausendstel für ein Eingabefeld: `780` → `0,78`, `null` → `''`. */
export function milliToInput(milli: number | null | undefined): string {
  if (milli === null || milli === undefined || !Number.isFinite(milli)) return ''
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 3 }).format(milli / 1000)
}

/** Eingabe zu Tausendstel: „0,78" → `780`. */
export function parseQuantityInput(raw: string): number | null {
  const cleaned = raw.trim().replace(/[\s\u00a0\u202f]/g, '')
  if (!cleaned) return null
  const normalized = cleaned.includes(',') ? cleaned.replace(/\./g, '').replace(',', '.') : cleaned
  const match = /^(\d*)(?:\.(\d{1,3}))?$/.exec(normalized)
  if (!match || (!match[1] && !match[2])) return null
  const whole = match[1] ? Number.parseInt(match[1], 10) : 0
  const fraction = (match[2] ?? '').padEnd(3, '0')
  return whole * 1000 + Number.parseInt(fraction, 10)
}

/** Basispunkte als Prozent: `2500` → `25,0 %`. */
export function formatBp(bp: number | null | undefined): string {
  if (bp === null || bp === undefined || !Number.isFinite(bp)) return PLACEHOLDER
  return `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(bp / 100)} %`
}

/** Basispunkte als Veränderung, mit Vorzeichen: `2000` → `+20,0 %`. */
export function formatBpSigned(bp: number | null | undefined): string {
  if (bp === null || bp === undefined || !Number.isFinite(bp)) return PLACEHOLDER
  const sign = bp > 0 ? '+' : ''
  return `${sign}${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(bp / 100)} %`
}

/** Anteil 0..1 aus Basispunkten — für Balkenbreiten. */
export function bpToFraction(bp: number | null | undefined): number {
  if (bp === null || bp === undefined || !Number.isFinite(bp)) return 0
  return Math.min(1, Math.max(0, bp / 10_000))
}
