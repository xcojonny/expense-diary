/**
 * Mehrbenutzerbetrieb im Frontend.
 *
 * Geprüft wird das, was still kaputtgehen kann: sieht man, in welchem Haushalt
 * man ist, trifft ein Wechsel wirklich den Server, und bekommt man im
 * SSO-Modus keine Passwortmaske vorgesetzt. Der API-Client ist ersetzt — hier
 * geht es um die Oberfläche, die Endpoints prüfen die Backend-Tests.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { navigation } from '@/lib/navigation'
import type { Health, SessionInfo } from '@/types/api'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  setActiveHousehold: vi.fn(),
}))

vi.mock('@/lib/api', () => {
  class ApiError extends Error {
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

  return {
    ApiError,
    UNAUTHORIZED_EVENT: 'expense-diary:unauthorized',
    api: {
      get: mocks.get,
      post: mocks.post,
      patch: mocks.patch,
      delete: mocks.remove,
    },
    setActiveHousehold: mocks.setActiveHousehold,
    fetchReceiptFile: vi.fn(),
  }
})

// Erst nach `vi.mock` importieren, damit der Store den ersetzten Client sieht.
const { useSession } = await import('@/stores/session')
const HouseholdSwitcher = (await import('@/components/HouseholdSwitcher.vue')).default
const LoginPage = (await import('@/pages/LoginPage.vue')).default
const InvitationPage = (await import('@/pages/InvitationPage.vue')).default

const HEALTH: Health = {
  status: 'ok',
  version: '2.0.0',
  auth_mode: 'oidc',
  multi_user: true,
  llm_provider: 'none',
  llm_ready: false,
  mail_ready: false,
  queued_jobs: 0,
}

function sessionInfo(overrides: Partial<SessionInfo> = {}): SessionInfo {
  return {
    authenticated: true,
    auth_mode: 'oidc',
    login_required: false,
    multi_user: true,
    sso_available: true,
    user: {
      id: 1,
      email: 'anna@example.org',
      display_name: 'Anna',
      memberships: [
        { household_id: 7, household_name: 'Zuhause', role: 'admin' },
        { household_id: 9, household_name: 'WG Bergstraße', role: 'member' },
      ],
    },
    active_household_id: 7,
    ...overrides,
  }
}

/** Store auf einen Serverstand bringen — über den echten `bootstrap`-Pfad. */
async function bootstrapWith(info: SessionInfo): Promise<void> {
  mocks.get.mockImplementation((path: string) => {
    if (path === '/auth/session') return Promise.resolve(info)
    if (path === '/health') return Promise.resolve(HEALTH)
    return Promise.reject(new Error(`unerwarteter Aufruf: ${path}`))
  })
  await useSession().bootstrap()
  await flushPromises()
}

/**
 * Router auf einem Pfad bereitstellen.
 *
 * Muss abgewartet werden: vor `isReady` ist `route.query` leer, und genau die
 * Query ist hier der Prüfgegenstand (Token, `sso_error`).
 */
async function testRouter(initial: string): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'overview', component: { template: '<div />' } },
      { path: '/login', name: 'login', component: { template: '<div />' } },
      { path: '/einladung', name: 'invitation', component: { template: '<div />' } },
    ],
  })
  await router.push(initial)
  await router.isReady()
  return router
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

describe('Session-Store', () => {
  it('kennt den aktiven Haushalt und die Rolle darin', async () => {
    await bootstrapWith(sessionInfo())
    const { activeMembership, isAdmin, memberships } = useSession()

    expect(memberships.value).toHaveLength(2)
    expect(activeMembership.value?.household_name).toBe('Zuhause')
    expect(isAdmin.value).toBe(true)
  })

  it('meldet für den Haushalt, in dem man nur Mitglied ist, keine Adminrechte', async () => {
    await bootstrapWith(sessionInfo({ active_household_id: 9 }))
    const { activeMembership, isAdmin } = useSession()

    expect(activeMembership.value?.household_name).toBe('WG Bergstraße')
    expect(isAdmin.value).toBe(false)
  })

  it('reicht den aktiven Haushalt an den API-Client durch', async () => {
    await bootstrapWith(sessionInfo())
    expect(mocks.setActiveHousehold).toHaveBeenCalledWith(7)
  })

  it('wechselt erst nach dem Serverruf — sonst zeigte die Ansicht fremde Zahlen', async () => {
    await bootstrapWith(sessionInfo())
    mocks.post.mockRejectedValueOnce(new Error('403'))

    await expect(useSession().switchHousehold(9)).rejects.toThrow()
    expect(useSession().activeHouseholdId.value).toBe(7)
  })

  it('übernimmt den neuen Haushalt nach erfolgreichem Wechsel', async () => {
    await bootstrapWith(sessionInfo())
    mocks.post.mockResolvedValueOnce({ id: 9, name: 'WG Bergstraße' })

    await useSession().switchHousehold(9)

    expect(mocks.post).toHaveBeenCalledWith('/households/9/activate')
    expect(useSession().activeHouseholdId.value).toBe(9)
    expect(mocks.setActiveHousehold).toHaveBeenLastCalledWith(9)
  })

  it('zeigt „Abmelden" nur, wo es etwas bewirkt', async () => {
    await bootstrapWith(sessionInfo({ auth_mode: 'oidc' }))
    expect(useSession().canLogout.value).toBe(true)

    await bootstrapWith(sessionInfo({ auth_mode: 'trusted_header', sso_available: false }))
    expect(useSession().canLogout.value).toBe(false)
  })
})

describe('HouseholdSwitcher', () => {
  it('zeigt bei einem Haushalt nur den Namen, ohne Menü', async () => {
    const info = sessionInfo()
    info.user!.memberships = [{ household_id: 7, household_name: 'Zuhause', role: 'admin' }]
    await bootstrapWith(info)

    const wrapper = mount(HouseholdSwitcher)
    expect(wrapper.text()).toContain('Zuhause')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('listet bei mehreren Haushalten alle auf und markiert den aktiven', async () => {
    await bootstrapWith(sessionInfo())
    const wrapper = mount(HouseholdSwitcher)

    await wrapper.find('.switcher__button').trigger('click')
    const items = wrapper.findAll('.menu__item')

    expect(items.map((item) => item.text())).toEqual(['Zuhause', 'WG Bergstraße'])
    expect(items[0].attributes('aria-selected')).toBe('true')
    expect(items[1].attributes('aria-selected')).toBe('false')
  })

  it('wechselt beim Klick und baut die Seite neu auf', async () => {
    await bootstrapWith(sessionInfo())
    const reload = vi.spyOn(navigation, 'reload').mockImplementation(() => {})
    mocks.post.mockResolvedValueOnce({ id: 9, name: 'WG Bergstraße' })

    const wrapper = mount(HouseholdSwitcher)
    await wrapper.find('.switcher__button').trigger('click')
    await wrapper.findAll('.menu__item')[1].trigger('click')
    await flushPromises()

    expect(mocks.post).toHaveBeenCalledWith('/households/9/activate')
    expect(reload).toHaveBeenCalledOnce()
  })

  it('ruft den Server nicht, wenn der schon aktive Haushalt gewählt wird', async () => {
    await bootstrapWith(sessionInfo())
    const wrapper = mount(HouseholdSwitcher)

    await wrapper.find('.switcher__button').trigger('click')
    await wrapper.findAll('.menu__item')[0].trigger('click')
    await flushPromises()

    expect(mocks.post).not.toHaveBeenCalled()
  })
})

describe('LoginPage', () => {
  it('zeigt im SSO-Modus einen Knopf statt eines Passwortfelds', async () => {
    await bootstrapWith(sessionInfo({ authenticated: false, user: null }))
    const wrapper = mount(LoginPage, { global: { plugins: [await testRouter('/login')] } })
    await flushPromises()

    expect(wrapper.find('input[type="password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Single Sign-on')
  })

  it('startet SSO als echte Navigation — eine Umleitung kann der Router nicht gehen', async () => {
    await bootstrapWith(sessionInfo({ authenticated: false, user: null }))
    const goto = vi.spyOn(navigation, 'goto').mockImplementation(() => {})

    const wrapper = mount(LoginPage, { global: { plugins: [await testRouter('/login')] } })
    await flushPromises()
    await wrapper.find('button').trigger('click')

    expect(goto).toHaveBeenCalledWith('/api/auth/oidc/login')
  })

  it('zeigt den Fehler, den der OIDC-Callback zurückgibt', async () => {
    await bootstrapWith(sessionInfo({ authenticated: false, user: null }))
    const router = await testRouter('/login?sso_error=Der%20Zugang%20ist%20deaktiviert.')

    const wrapper = mount(LoginPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Der Zugang ist deaktiviert.')
  })

  it('erklärt auf dem Einladungslink, warum hier ein Login steht', async () => {
    await bootstrapWith(sessionInfo({ authenticated: false, user: null }))
    const wrapper = mount(LoginPage, {
      global: { plugins: [await testRouter('/einladung?token=abc12345')] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('eingeladen')
  })

  it('zeigt im Passwortmodus das Passwortfeld', async () => {
    await bootstrapWith(
      sessionInfo({
        authenticated: false,
        user: null,
        auth_mode: 'password',
        login_required: true,
        multi_user: false,
        sso_available: false,
      }),
    )
    const wrapper = mount(LoginPage, { global: { plugins: [await testRouter('/login')] } })
    await flushPromises()

    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Single Sign-on')
  })
})

describe('InvitationPage', () => {
  it('löst den Token aus der URL ein und begrüßt im neuen Haushalt', async () => {
    await bootstrapWith(sessionInfo())
    mocks.post.mockResolvedValueOnce(sessionInfo({ active_household_id: 9 }))

    const wrapper = mount(InvitationPage, {
      global: { plugins: [await testRouter('/einladung?token=geheim-123')] },
    })
    await flushPromises()

    expect(mocks.post).toHaveBeenCalledWith('/auth/invitations/accept', { token: 'geheim-123' })
    expect(wrapper.text()).toContain('WG Bergstraße')
  })

  it('nennt den Grund, wenn der Token nicht mehr gilt', async () => {
    await bootstrapWith(sessionInfo())
    const { ApiError } = await import('@/lib/api')
    mocks.post.mockRejectedValueOnce(new ApiError(400, 'Diese Einladung ist abgelaufen.'))

    const wrapper = mount(InvitationPage, {
      global: { plugins: [await testRouter('/einladung?token=alt')] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Diese Einladung ist abgelaufen.')
  })

  it('verlangt einen Token in der URL', async () => {
    await bootstrapWith(sessionInfo())

    const wrapper = mount(InvitationPage, {
      global: { plugins: [await testRouter('/einladung')] },
    })
    await flushPromises()

    expect(mocks.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('keinen Einladungscode')
  })
})
