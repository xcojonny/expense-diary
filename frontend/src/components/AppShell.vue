<script setup lang="ts">
/**
 * Navigation: Sidebar auf Desktop, Bottom-Navigation plus Kamera-Knopf auf
 * Mobil.
 *
 * Der Altstand hatte sieben umbrechende Textlinks ohne Active-State — auf dem
 * Handy fraßen sie zwei Zeilen, und man sah nie, wo man ist. Weil die App als
 * PWA installiert wird, ist die Bottom-Navigation hier die richtige Bauform:
 * Daumenreichweite, sichtbarer Zustand, ein Griff zur Kamera.
 */
import { computed } from 'vue'
import { RouteRecordName, useRoute } from 'vue-router'

import { useSession } from '@/stores/session'
import { applyTheme, theme } from '@/lib/theme'
import UiButton from '@/ui/UiButton.vue'
import UiIcon from '@/ui/UiIcon.vue'

const route = useRoute()
const { logout, loginRequired, health } = useSession()

interface NavEntry {
  to: string
  label: string
  icon: string
  /** Auf Mobil zeigt die Bottom-Navigation nur vier Ziele. */
  primary: boolean
  name: RouteRecordName
}

const NAV: NavEntry[] = [
  { to: '/', label: 'Übersicht', icon: 'home', primary: true, name: 'overview' },
  { to: '/bons', label: 'Bons', icon: 'receipt', primary: true, name: 'receipts' },
  { to: '/bericht', label: 'Bericht', icon: 'chart', primary: true, name: 'report' },
  { to: '/kategorien', label: 'Kategorien', icon: 'tag', primary: false, name: 'categories' },
  { to: '/einstellungen', label: 'Mehr', icon: 'settings', primary: true, name: 'settings' },
]

const primaryNav = computed(() => NAV.filter((entry) => entry.primary))

const themeIcon = computed(() => (theme.value === 'dark' ? 'moon' : 'sun'))

function cycleTheme(): void {
  const order = ['system', 'light', 'dark'] as const
  const next = order[(order.indexOf(theme.value) + 1) % order.length]
  applyTheme(next)
}

const themeTitle = computed(
  () =>
    ({ system: 'Design: System', light: 'Design: Hell', dark: 'Design: Dunkel' })[theme.value],
)

/** Offene Jobs anzeigen, damit „warum tut sich nichts?" beantwortet ist. */
const queued = computed(() => health.value?.queued_jobs ?? 0)
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand__mark"><UiIcon name="receipt" :size="17" /></span>
        <span class="brand__text">Haushaltsbuch</span>
      </RouterLink>

      <nav class="sidenav" aria-label="Hauptnavigation">
        <RouterLink
          v-for="entry in NAV"
          :key="entry.to"
          :to="entry.to"
          class="sidenav__link"
          :class="{ 'sidenav__link--active': route.name === entry.name }"
        >
          <UiIcon :name="entry.icon" :size="17" />
          <span>{{ entry.label === 'Mehr' ? 'Einstellungen' : entry.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar__foot">
        <RouterLink to="/upload" class="sidebar__cta">
          <UiIcon name="camera" :size="17" />
          <span>Bon erfassen</span>
        </RouterLink>
        <div class="sidebar__tools">
          <UiButton variant="ghost" size="sm" :title="themeTitle" @click="cycleTheme">
            <UiIcon :name="themeIcon" :size="16" />
            <span class="sr-only">Design wechseln</span>
          </UiButton>
          <UiButton v-if="loginRequired" variant="ghost" size="sm" title="Abmelden" @click="logout">
            <UiIcon name="logout" :size="16" />
            <span class="sr-only">Abmelden</span>
          </UiButton>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <RouterLink to="/" class="topbar__brand">
          <span class="brand__mark"><UiIcon name="receipt" :size="15" /></span>
          Haushaltsbuch
        </RouterLink>
        <div class="row">
          <span v-if="queued > 0" class="topbar__queue" :title="`${queued} Bon(s) in Arbeit`">
            <UiIcon name="clock" :size="14" />
            {{ queued }}
          </span>
          <UiButton variant="ghost" size="sm" :title="themeTitle" @click="cycleTheme">
            <UiIcon :name="themeIcon" :size="16" />
            <span class="sr-only">Design wechseln</span>
          </UiButton>
        </div>
      </header>

      <main class="content">
        <slot />
      </main>
    </div>

    <nav class="bottomnav" aria-label="Hauptnavigation (mobil)">
      <RouterLink
        v-for="entry in primaryNav"
        :key="entry.to"
        :to="entry.to"
        class="bottomnav__link"
        :class="{ 'bottomnav__link--active': route.name === entry.name }"
      >
        <UiIcon :name="entry.icon" :size="20" />
        <span>{{ entry.label }}</span>
      </RouterLink>
    </nav>

    <RouterLink to="/upload" class="fab" aria-label="Bon erfassen">
      <UiIcon name="camera" :size="23" />
    </RouterLink>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100dvh;
}

/* --- Sidebar (Desktop) ---------------------------------------------------- */

.sidebar {
  display: none;
  flex-direction: column;
  gap: 20px;
  width: var(--sidebar-width);
  flex: none;
  padding: 18px 14px;
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.brand {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 0 6px;
  color: var(--text);
  font-weight: 620;
  letter-spacing: -0.012em;
  text-decoration: none;
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  color: var(--accent-fg);
  background: var(--accent);
  border-radius: 9px;
}

.sidenav {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.sidenav__link {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-muted);
  text-decoration: none;
  transition:
    background var(--transition),
    color var(--transition);
}

.sidenav__link:hover {
  background: var(--surface-hover);
  color: var(--text);
  text-decoration: none;
}

.sidenav__link--active {
  background: var(--accent-soft);
  color: var(--accent);
}

.sidebar__foot {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sidebar__cta {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 10px;
  background: var(--accent);
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  font-weight: 560;
  color: var(--accent-fg);
  text-decoration: none;
}

.sidebar__cta:hover {
  background: var(--accent-hover);
  text-decoration: none;
}

.sidebar__tools {
  display: flex;
  gap: 4px;
  justify-content: center;
}

/* --- Hauptbereich --------------------------------------------------------- */

.main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  /* Auf Mobil bleibt der Kopf stehen: Titel und Design-Schalter sind immer da. */
  position: sticky;
  top: 0;
  z-index: 20;
}

.topbar__brand {
  display: flex;
  gap: 8px;
  align-items: center;
  color: var(--text);
  font-weight: 600;
  text-decoration: none;
}

.topbar__queue {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 3px 8px;
  background: var(--info-soft);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 550;
  color: var(--info);
}

.content {
  /* Inhaltsbreite: 1240 px statt der 768 px des Altstands — eine Analyse-App
     braucht Platz für zwei Spalten. */
  width: 100%;
  max-width: var(--content-max);
  padding: 16px 14px calc(var(--bottom-nav-height) + 26px);
  margin: 0 auto;
}

/* --- Bottom-Navigation (Mobil) ------------------------------------------- */

.bottomnav {
  position: fixed;
  bottom: 0;
  left: 0;
  z-index: 30;
  display: flex;
  width: 100%;
  height: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: var(--surface);
  border-top: 1px solid var(--border);
}

.bottomnav__link {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 550;
  color: var(--text-subtle);
  text-decoration: none;
}

/* Lücke in der MITTE (nach dem zweiten von vier Zielen) — dort sitzt der
   Kamera-Knopf, der horizontal zentriert ist. Sitzt die Lücke woanders,
   überdeckt der Knopf eine Beschriftung. */
.bottomnav__link:nth-child(2) {
  margin-right: 58px;
}

.bottomnav__link--active {
  color: var(--accent);
}

.bottomnav__link:hover {
  text-decoration: none;
}

.fab {
  position: fixed;
  right: 50%;
  bottom: calc(var(--bottom-nav-height) - 18px + env(safe-area-inset-bottom));
  z-index: 40;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  color: var(--accent-fg);
  background: var(--accent);
  border: 3px solid var(--surface);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow);
  transform: translateX(50%);
}

.fab:hover {
  background: var(--accent-hover);
}

/* --- Umschaltpunkt ------------------------------------------------------- */

@media (width >= 900px) {
  .sidebar {
    display: flex;
  }

  .topbar,
  .bottomnav,
  .fab {
    display: none;
  }

  .content {
    padding: 24px 28px 40px;
  }
}
</style>
