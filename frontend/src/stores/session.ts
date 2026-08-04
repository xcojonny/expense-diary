/**
 * Session-Zustand.
 *
 * Bewusst ein Modul mit `ref`s statt Pinia: es gibt zwei Zustände (Session,
 * Kategorien), und beide brauchen weder Devtools-Zeitreise noch SSR-Isolierung.
 */

import { computed, ref } from 'vue'

import { api } from '@/lib/api'
import type { Health, SessionInfo } from '@/types/api'

const session = ref<SessionInfo | null>(null)
const health = ref<Health | null>(null)
const ready = ref(false)

export const useSession = () => ({
  session: computed(() => session.value),
  health: computed(() => health.value),
  ready: computed(() => ready.value),

  authenticated: computed(() => session.value?.authenticated ?? false),
  /** Nur im Passwort-Modus gibt es überhaupt eine Anmeldemaske (ADR-004). */
  loginRequired: computed(() => session.value?.login_required ?? true),
  authMode: computed(() => session.value?.auth_mode ?? 'password'),

  async bootstrap(): Promise<void> {
    try {
      session.value = await api.get<SessionInfo>('/auth/session')
    } catch {
      session.value = { authenticated: false, auth_mode: 'password', login_required: true }
    } finally {
      ready.value = true
    }
    if (session.value.authenticated) void loadHealth()
  },

  async login(password: string): Promise<void> {
    session.value = await api.post<SessionInfo>(
      '/auth/login',
      { password },
      { silentUnauthorized: true },
    )
    void loadHealth()
  },

  async logout(): Promise<void> {
    try {
      await api.post<void>('/auth/logout')
    } finally {
      session.value = session.value
        ? { ...session.value, authenticated: false }
        : { authenticated: false, auth_mode: 'password', login_required: true }
      health.value = null
    }
  },

  /** Vom 401-Handler benutzt: Sitzung als beendet markieren, ohne Serverrunde. */
  markUnauthenticated(): void {
    if (session.value?.authenticated) {
      session.value = { ...session.value, authenticated: false }
    }
    health.value = null
  },

  refreshHealth: loadHealth,
})

async function loadHealth(): Promise<void> {
  try {
    health.value = await api.get<Health>('/health')
  } catch {
    health.value = null
  }
}
