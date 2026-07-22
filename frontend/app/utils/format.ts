// Decimals arrive from the API as strings; format them for display here.

const EUR = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })

export function eur(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isNaN(n) ? '—' : EUR.format(n)
}

export function pct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isNaN(n) ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(1)} %`
}

const MONTHS = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

export function monthName(month: number): string {
  return MONTHS[month - 1] ?? String(month)
}
