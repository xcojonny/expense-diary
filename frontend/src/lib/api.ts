/**
 * API-Client.
 *
 * Session steckt im httpOnly-Cookie, das der Browser mitschickt — es gibt kein
 * Token im JavaScript und damit auch keinen Refresh-Tanz. Bei 401 wird ein
 * Event ausgelöst, auf das die App mit einem Sprung zum Login reagiert.
 */

const BASE = '/api'

/** Header, mit dem der Server den Mandanten bestimmt (siehe `api/deps.py`). */
const HOUSEHOLD_HEADER = 'X-Household-Id'

/**
 * Aktiver Haushalt.
 *
 * Der Server merkt sich die Auswahl zwar in einem Cookie, aber der Header
 * gewinnt — und nur der Header ist synchron. Beim Wechsel würde sonst die
 * Anfrage, die direkt nach dem Klick startet, noch den alten Haushalt treffen.
 * Der Wert liegt hier statt im Session-Store, damit `api` nichts importieren
 * muss (sonst hätten die beiden Module einen Zyklus).
 */
let activeHousehold: number | null = null

export function setActiveHousehold(id: number | null): void {
  activeHousehold = id
}

function householdHeaders(): Record<string, string> {
  return activeHousehold === null ? {} : { [HOUSEHOLD_HEADER]: String(activeHousehold) }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }
}

/** Wird bei 401 ausgelöst; `App.vue` hört darauf und zeigt den Login. */
export const UNAUTHORIZED_EVENT = 'expense-diary:unauthorized'

interface RequestOptions {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  /** Bei `true` löst ein 401 kein globales Abmelden aus (für den Login selbst). */
  silentUnauthorized?: boolean
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  return url.pathname + url.search
}

async function extractMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    // Pydantic-Validierungsfehler kommen als Liste.
    if (Array.isArray(data?.detail) && data.detail.length) {
      const first = data.detail[0]
      return typeof first?.msg === 'string' ? first.msg : 'Ungültige Eingabe.'
    }
  } catch {
    /* keine JSON-Antwort — Standardtext unten */
  }
  return response.status >= 500
    ? 'Der Server hat einen Fehler gemeldet.'
    : 'Die Anfrage wurde abgelehnt.'
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, silentUnauthorized } = options

  const init: RequestInit = { method, credentials: 'same-origin', headers: householdHeaders() }
  if (body instanceof FormData) {
    init.body = body // Content-Type setzt der Browser samt boundary
  } else if (body !== undefined) {
    init.headers = { ...householdHeaders(), 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), init)
  } catch {
    throw new ApiError(0, 'Keine Verbindung zum Server.')
  }

  if (response.status === 401 && !silentUnauthorized) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }
  if (!response.ok) {
    throw new ApiError(response.status, await extractMessage(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query']) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown, extra?: RequestOptions) =>
    request<T>(path, { method: 'POST', body, ...extra }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/**
 * Beleg-Datei als Blob-URL.
 *
 * Der Endpoint ist authentifiziert, also kann kein `<img src>` direkt darauf
 * zeigen — die Bytes werden geholt und als `blob:`-URL gerendert. Der Aufrufer
 * muss die URL per `URL.revokeObjectURL` freigeben.
 */
export async function fetchReceiptFile(receiptId: number): Promise<{ url: string; type: string }> {
  const response = await fetch(`${BASE}/receipts/${receiptId}/file`, {
    credentials: 'same-origin',
    headers: householdHeaders(),
  })
  if (!response.ok) {
    throw new ApiError(response.status, 'Beleg konnte nicht geladen werden.')
  }
  const blob = await response.blob()
  return { url: URL.createObjectURL(blob), type: blob.type }
}
