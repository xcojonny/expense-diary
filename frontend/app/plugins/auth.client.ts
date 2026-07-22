import { useAuthStore } from '~/stores/auth'

// Bootstrap the session before the app renders: attempt a refresh (httpOnly
// cookie) to obtain an access token + load the current user. SPA-only.
export default defineNuxtPlugin(async () => {
  await useAuthStore().bootstrap()
})
