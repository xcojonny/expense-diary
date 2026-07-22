import { useAuthStore } from '~/stores/auth'

// Route guard: everything except the login page requires an authenticated
// session. The auth plugin has already bootstrapped by the time this runs.
export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuthStore()
  if (to.path === '/login') return
  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/login', query: to.path === '/' ? {} : { redirect: to.path } })
  }
})
