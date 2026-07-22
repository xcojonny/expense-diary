import { useAuthStore } from '~/stores/auth'

type FetchOptions = Record<string, unknown>

function statusOf(error: unknown): number | undefined {
  const e = error as { status?: number; response?: { status?: number } }
  return e?.response?.status ?? e?.status
}

// Typed fetch against /api/v1 that attaches the access token + active-group
// header, and transparently refreshes once on a 401 (expired access token).
export function useApi() {
  const auth = useAuthStore()

  async function api<T>(path: string, opts: FetchOptions = {}): Promise<T> {
    const build = (): Record<string, string> => {
      const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) }
      if (auth.accessToken) headers.Authorization = `Bearer ${auth.accessToken}`
      if (auth.activeGroupId) headers['X-Group-Id'] = auth.activeGroupId
      return headers
    }
    try {
      return await $fetch<T>(path, { baseURL: '/api/v1', ...opts, headers: build() })
    } catch (error) {
      if (statusOf(error) === 401 && (await auth.tryRefresh())) {
        return await $fetch<T>(path, { baseURL: '/api/v1', ...opts, headers: build() })
      }
      throw error
    }
  }

  return { api }
}
