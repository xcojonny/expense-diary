import tailwindcss from '@tailwindcss/vite'

// Backend port for the dev proxy — default :8000, overridable when taken
// (see Makefile: `make dev-backend dev-frontend BACKEND_PORT=8010`).
const backendPort = process.env.BACKEND_PORT || 8000
const backend = `http://localhost:${backendPort}`

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  // Private, self-hosted instance: SPA instead of SSR — simpler PWA/offline
  // behavior and no Node server to operate.
  ssr: false,

  srcDir: 'app/',
  compatibilityDate: '2025-07-01',

  modules: ['@pinia/nuxt', '@vite-pwa/nuxt', '@nuxt/eslint'],

  css: ['~/assets/css/main.css'],

  vite: {
    plugins: [tailwindcss()],
    // Dev proxy: the SPA talks to the backend on the same origin in prod
    // (Traefik/nginx), so mirror that locally instead of hard-coding a host.
    server: {
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/media': { target: backend, changeOrigin: true },
      },
    },
  },

  runtimeConfig: {
    public: {
      gitSha: process.env.GIT_SHA || '',
    },
  },

  typescript: {
    strict: true,
    typeCheck: false, // separate `pnpm typecheck` step (CI)
  },

  app: {
    head: {
      title: 'Haushaltsbuch',
      htmlAttrs: { lang: 'de' },
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#16a34a' },
        { name: 'mobile-web-app-capable', content: 'yes' },
      ],
    },
  },

  pwa: {
    registerType: 'autoUpdate',
    manifest: {
      name: 'Haushaltsbuch',
      short_name: 'Haushaltsbuch',
      lang: 'de',
      theme_color: '#16a34a',
      background_color: '#ffffff',
      display: 'standalone',
    },
    // SPA build (ssr:false) → single-page app fallback for offline navigation.
    devOptions: { enabled: false },
  },
})
