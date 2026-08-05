/**
 * Session-Zustand: wer ist angemeldet, in welchem Haushalt.
 *
 * Bewusst ein Modul mit `ref`s statt Pinia: es gibt zwei Zustände (Session,
 * Kategorien), und beide brauchen weder Devtools-Zeitreise noch SSR-Isolierung.
 *
 * Der aktive Haushalt wird hier gehalten und an `api` durchgereicht, damit
 * jede Anfrage denselben Mandanten trifft wie die Ansicht, die sie ausgelöst
 * hat.
 */

import { computed, ref } from 'vue'

import { api, setActiveHousehold } from '@/lib/api'
import type { Health, Membership, SessionInfo } from '@/types/api'

const ANONYMOUS: SessionInfo = {
  authenticated: false,
  auth_mode: 'password',
  login_required: true,
  multi_user: false,
  sso_available: false,
  user: null,
  active_household_id: null,
}

const session = ref<SessionInfo | null>(null)
const health = ref<Health | null>(null)
const ready = ref(false)

/** Session übernehmen und `api` auf denselben Haushalt zeigen lassen. */
function adopt(info: SessionInfo): void {
  session.value = info
  setActiveHousehold(info.active_household_id)
}

export const useSession = () => ({
  session: computed(() => session.value),
  health: computed(() => health.value),
  ready: computed(() => ready.value),

  authenticated: computed(() => session.value?.authenticated ?? false),
  /** Nur im Passwort-Modus gibt es überhaupt eine Anmeldemaske (ADR-004). */
  loginRequired: computed(() => session.value?.login_required ?? true),
  authMode: computed(() => session.value?.auth_mode ?? 'password'),
  multiUser: computed(() => session.value?.multi_user ?? false),
  ssoAvailable: computed(() => session.value?.sso_available ?? false),
  /**
   * Abmelden zeigen wir nur, wo es etwas bewirkt: `password` und `oidc` haben
   * ein Cookie, das man wegwerfen kann. Bei `trusted_header` würde der Proxy
   * bei der nächsten Anfrage sofort wieder anmelden, bei `none` gibt es nichts
   * abzumelden — ein Knopf, der nichts tut, ist schlimmer als keiner.
   */
  canLogout: computed(
    () => session.value?.auth_mode === 'password' || session.value?.auth_mode === 'oidc',
  ),

  user: computed(() => session.value?.user ?? null),
  memberships: computed<Membership[]>(() => session.value?.user?.memberships ?? []),
  activeHouseholdId: computed(() => session.value?.active_household_id ?? null),
  activeMembership: computed(() =>
    (session.value?.user?.memberships ?? []).find(
      (member) => member.household_id === session.value?.active_household_id,
    ),
  ),
  /** Verwaltungsknöpfe zeigen nur, wer im aktiven Haushalt Admin ist. */
  isAdmin: computed(
    () =>
      (session.value?.user?.memberships ?? []).find(
        (member) => member.household_id === session.value?.active_household_id,
      )?.role === 'admin',
  ),

  async bootstrap(): Promise<void> {
    try {
      adopt(await api.get<SessionInfo>('/auth/session'))
    } catch {
      adopt({ ...ANONYMOUS })
    } finally {
      ready.value = true
    }
    if (session.value?.authenticated) void loadHealth()
  },

  /** Session neu laden, z. B. nachdem ein Haushalt umbenannt oder gelöscht wurde. */
  async refresh(): Promise<void> {
    adopt(await api.get<SessionInfo>('/auth/session'))
  },

  async login(password: string): Promise<void> {
    adopt(
      await api.post<SessionInfo>('/auth/login', { password }, { silentUnauthorized: true }),
    )
    void loadHealth()
  },

  async logout(): Promise<void> {
    try {
      await api.post<void>('/auth/logout')
    } finally {
      adopt({ ...ANONYMOUS, auth_mode: session.value?.auth_mode ?? 'password' })
      health.value = null
    }
  },

  /**
   * Haushalt wechseln.
   *
   * Erst der Server (setzt das Cookie, prüft die Mitgliedschaft), dann der
   * lokale Zustand — schlägt der Wechsel fehl, bleibt die Ansicht dort, wo sie
   * war, statt Daten eines Haushalts zu zeigen, den man nicht hat.
   */
  async switchHousehold(householdId: number): Promise<void> {
    await api.post(`/households/${householdId}/activate`)
    if (session.value) {
      adopt({ ...session.value, active_household_id: householdId })
    }
  },

  /** Einladung einlösen; die Antwort enthält den neuen Haushalt als aktiven. */
  async acceptInvitation(token: string): Promise<SessionInfo> {
    const info = await api.post<SessionInfo>('/auth/invitations/accept', { token })
    adopt(info)
    return info
  },

  /** Vom 401-Handler benutzt: Sitzung als beendet markieren, ohne Serverrunde. */
  markUnauthenticated(): void {
    if (session.value?.authenticated) {
      adopt({ ...session.value, authenticated: false })
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
