/**
 * Eine Ressource = ein Widget.
 *
 * Der Altstand lud Dashboard und Bericht über ein `Promise.all` von drei bzw.
 * vier Endpoints. Fiel einer aus, war die ganze Seite leer — `bericht.vue`
 * behandelte `error` nicht einmal. Hier lädt jedes Widget für sich und zeigt
 * seinen eigenen Skeleton-, Fehler- und Leerzustand.
 */

import { ref, shallowRef, watch, type Ref, type WatchSource } from 'vue'

import { ApiError } from './api'

export interface Resource<T> {
  data: Ref<T | null>
  error: Ref<string | null>
  /** `true` während des ersten Ladens — dafür ist der Skeleton da. */
  loading: Ref<boolean>
  /** `true` beim Nachladen, wenn schon Daten stehen — dezenter Hinweis. */
  refreshing: Ref<boolean>
  reload: () => Promise<void>
}

export interface ResourceOptions {
  /** Neu laden, wenn sich eine dieser Quellen ändert (z. B. der Monat). */
  watch?: WatchSource[]
  /** Nicht sofort laden (z. B. erst nach einer Auswahl). */
  lazy?: boolean
}

export function useResource<T>(
  loader: () => Promise<T>,
  options: ResourceOptions = {},
): Resource<T> {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  const refreshing = ref(false)

  // Läufe durchzählen: eine langsame ältere Antwort darf eine neuere nicht
  // überschreiben (klassisches Wettrennen beim Monatswechsel).
  let run = 0

  async function reload(): Promise<void> {
    const current = ++run
    error.value = null
    if (data.value === null) loading.value = true
    else refreshing.value = true

    try {
      const result = await loader()
      if (current !== run) return
      data.value = result
    } catch (caught) {
      if (current !== run) return
      // 401 behandelt die App global (Sprung zum Login) — hier keine
      // Fehlermeldung zeigen, die sofort wieder verschwindet.
      if (caught instanceof ApiError && caught.isUnauthorized) return
      error.value = caught instanceof Error ? caught.message : 'Unbekannter Fehler.'
    } finally {
      if (current === run) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  if (!options.lazy) void reload()
  if (options.watch?.length) {
    watch(options.watch, () => void reload())
  }

  return { data, error, loading, refreshing, reload }
}
