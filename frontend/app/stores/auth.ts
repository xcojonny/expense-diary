import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Me } from '~/types/models'

interface Session {
  access_token: string
}

// Session lives in memory (SPA); the refresh token is an httpOnly cookie the
// browser sends to /auth/*. On load we bootstrap by attempting a refresh.
export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const user = ref<Me | null>(null)
  const activeGroupId = ref<string | null>(null)
  const ready = ref(false)

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)

  function headers(): Record<string, string> {
    return accessToken.value ? { Authorization: `Bearer ${accessToken.value}` } : {}
  }

  async function tryRefresh(): Promise<boolean> {
    try {
      const s = await $fetch<Session>('/api/v1/auth/refresh', { method: 'POST' })
      accessToken.value = s.access_token
      return true
    } catch {
      accessToken.value = null
      return false
    }
  }

  async function fetchMe(): Promise<void> {
    const me = await $fetch<Me>('/api/v1/me', { headers: headers() })
    user.value = me
    if (!activeGroupId.value && me.memberships.length) {
      activeGroupId.value = me.memberships[0]!.group_id
    }
  }

  async function bootstrap(): Promise<void> {
    if (await tryRefresh()) {
      try {
        await fetchMe()
      } catch {
        accessToken.value = null
        user.value = null
      }
    }
    ready.value = true
  }

  async function requestMagicLink(email: string): Promise<void> {
    await $fetch('/api/v1/auth/magic-link', { method: 'POST', body: { email } })
  }

  // Verifying a link either logs this browser in (bound browser → session) or
  // returns a pairing code to type into the requesting browser.
  async function verify(token: string): Promise<{ status: string; code?: string }> {
    const r = await $fetch<{ status: string; access_token?: string; code?: string }>(
      '/api/v1/auth/verify',
      { method: 'POST', body: { token } },
    )
    if (r.status === 'session' && r.access_token) {
      accessToken.value = r.access_token
      await fetchMe()
    }
    return { status: r.status, code: r.code }
  }

  async function verifyCode(code: string): Promise<void> {
    const s = await $fetch<Session>('/api/v1/auth/verify-code', { method: 'POST', body: { code } })
    accessToken.value = s.access_token
    await fetchMe()
  }

  async function loginStatus(): Promise<string> {
    const r = await $fetch<{ status: string }>('/api/v1/auth/login-status', { method: 'POST' })
    return r.status
  }

  async function acceptInvite(token: string): Promise<void> {
    const s = await $fetch<Session>('/api/v1/auth/invitations/accept', {
      method: 'POST',
      body: { token },
    })
    accessToken.value = s.access_token
    await fetchMe()
  }

  function setActiveGroup(id: string): void {
    activeGroupId.value = id
  }

  async function logout(): Promise<void> {
    try {
      await $fetch('/api/v1/auth/logout', { method: 'POST' })
    } finally {
      accessToken.value = null
      user.value = null
      activeGroupId.value = null
    }
  }

  return {
    accessToken,
    user,
    activeGroupId,
    ready,
    isAuthenticated,
    tryRefresh,
    fetchMe,
    bootstrap,
    requestMagicLink,
    verify,
    verifyCode,
    loginStatus,
    acceptInvite,
    setActiveGroup,
    logout,
  }
})
