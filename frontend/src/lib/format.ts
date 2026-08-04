/** Datums- und Textformatierung (deutsch). */

export const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

const DATE = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
const DATE_SHORT = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit' })
const DATE_TIME = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function monthName(month: number): string {
  return MONTH_NAMES[month - 1] ?? String(month)
}

export function monthLabel(year: number, month: number): string {
  return `${monthName(month)} ${year}`
}

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatDate(value: string | null | undefined): string {
  const date = toDate(value)
  return date ? DATE.format(date) : '—'
}

export function formatDateShort(value: string | null | undefined): string {
  const date = toDate(value)
  return date ? DATE_SHORT.format(date) : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  const date = toDate(value)
  return date ? DATE_TIME.format(date) : '—'
}

/** Für `<input type="date">`: ISO-Datumsanteil. */
export function toDateInput(value: string | null | undefined): string {
  const date = toDate(value)
  if (!date) return ''
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** Aus `<input type="date">` zurück — als lokale Mitternacht, ohne Zeitzonen-
 *  Verschiebung (die einen Einkauf sonst auf den Vortag rutschen lässt). */
export function fromDateInput(value: string): string | null {
  if (!value) return null
  return `${value}T00:00:00`
}

/** „vor 3 Minuten" — für Uploads, die gerade laufen. */
export function relativeTime(value: string | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'gerade eben'
  if (seconds < 3600) return `vor ${Math.floor(seconds / 60)} min`
  if (seconds < 86_400) return `vor ${Math.floor(seconds / 3600)} h`
  return formatDate(value)
}

export function pluralize(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}
