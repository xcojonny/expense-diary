import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Der Build landet direkt im Backend — von dort liefert FastAPI ihn aus
// (ADR-006). Damit gibt es keinen nginx-Container und keine Möglichkeit, dass
// API und Frontend in unterschiedlichen Versionen laufen.
const OUT_DIR = fileURLToPath(new URL('../backend/app/static', import.meta.url))

const API_TARGET = process.env.API_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'Haushaltsbuch',
        short_name: 'Haushalt',
        description: 'Kassenbon fotografieren, Ausgaben und Preistrends auswerten.',
        lang: 'de',
        start_url: '/',
        display: 'standalone',
        background_color: '#f4f6f5', // = --bg (siehe tokens.css)
        theme_color: '#0f8a6a', // = --accent
        // Der Altstand deklarierte keine Icons — der Installationsdialog blieb
        // dadurch kaputt.
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/index.html',
        // Nie API-Antworten cachen: ein Haushaltsbuch, das gestrige Zahlen
        // zeigt, ist schlimmer als eines, das offline nichts zeigt.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
      },
    }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: OUT_DIR,
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    // In Produktion liegen API und SPA auf derselben Herkunft. Der Dev-Proxy
    // spiegelt das, damit es lokal keine CORS-Sonderbehandlung braucht.
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
