/**
 * Routen — ausdrücklich statt datei-basiert (ADR-005).
 *
 * Bei elf Seiten ist eine Tabelle lesbarer als Dateimagie: man sieht Pfad,
 * Name und Komponente an einer Stelle. Alle Seiten werden lazy geladen, damit
 * der erste Aufruf nur die Übersicht lädt.
 */
import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('@/pages/OverviewPage.vue'),
      meta: { title: 'Übersicht' },
    },
    {
      path: '/upload',
      name: 'upload',
      component: () => import('@/pages/UploadPage.vue'),
      meta: { title: 'Bon erfassen' },
    },
    {
      path: '/bons',
      name: 'receipts',
      component: () => import('@/pages/ReceiptsPage.vue'),
      meta: { title: 'Bons' },
    },
    {
      path: '/bons/:id(\\d+)',
      name: 'receipt-detail',
      component: () => import('@/pages/ReceiptDetailPage.vue'),
      meta: { title: 'Bon' },
    },
    {
      path: '/bericht',
      name: 'report',
      component: () => import('@/pages/ReportPage.vue'),
      meta: { title: 'Bericht' },
    },
    {
      path: '/kategorien',
      name: 'categories',
      component: () => import('@/pages/CategoriesPage.vue'),
      meta: { title: 'Kategorien' },
    },
    {
      path: '/einstellungen',
      name: 'settings',
      component: () => import('@/pages/SettingsPage.vue'),
      meta: { title: 'Einstellungen' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/pages/NotFoundPage.vue'),
      meta: { title: 'Nicht gefunden' },
    },
  ],
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · Haushaltsbuch` : 'Haushaltsbuch'
})
