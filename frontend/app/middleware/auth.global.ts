import { samePath } from '~/utils/routing'
import { useAuthStore } from '~/stores/auth'

// Route guard: everything except the login page requires an authenticated
// session. The auth plugin has already bootstrapped by the time this runs.
// The login check is trailing-slash-insensitive: a proxy directory-redirect can
// deliver `/login/`, and bouncing that would strip the magic-link ?token.
export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuthStore()
  if (samePath(to.path, '/login')) return
  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/login', query: to.path === '/' ? {} : { redirect: to.path } })
  }
})
