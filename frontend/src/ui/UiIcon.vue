<script setup lang="ts">
/**
 * Inline-SVG-Icons statt Icon-Bibliothek (spart eine Abhängigkeit für ~20
 * Symbole). Alle auf 24×24-Raster, `currentColor`, gleiche Strichstärke.
 */
import { computed } from 'vue'

const PATHS: Record<string, string> = {
  home: 'M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5',
  receipt: 'M6 2.5h12v19l-3-2-3 2-3-2-3 2v-19ZM9.5 8h5M9.5 12h5M9.5 16h3',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  tag: 'M3 12.5V4.5A1.5 1.5 0 0 1 4.5 3h8l8.5 8.5-9 9L3 12.5ZM7.5 7.5h.01',
  settings:
    'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3H9.8l-.4 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.7h4.4l.4-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.06-.4.1-.8.1-1.2Z',
  camera: 'M3 8.5A2 2 0 0 1 5 6.5h1.8l1.2-2h8l1.2 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9ZM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
  upload: 'M12 16V4M12 4 7.5 8.5M12 4l4.5 4.5M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  check: 'M4.5 12.5 9.5 17.5 19.5 6.5',
  x: 'M6 6l12 12M18 6 6 18',
  chevronLeft: 'M15 5l-7 7 7 7',
  chevronRight: 'M9 5l7 7-7 7',
  chevronDown: 'M5 9l7 7 7-7',
  trash: 'M4 7h16M9 7V4.5h6V7M6.5 7l.8 13h9.4l.8-13M10.5 11v5.5M13.5 11v5.5',
  edit: 'M4 20h4L20 8l-4-4L4 16v4ZM14.5 5.5 18.5 9.5',
  refresh: 'M20 12a8 8 0 1 1-2.4-5.7M20 3.5V8h-4.5',
  warning: 'M12 3 2.5 20h19L12 3ZM12 9v5M12 17.2h.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5.5M12 7.7h.01',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7.5V12l3.5 2',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13ZM15.5 15.5 20 20',
  sun: 'M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9ZM12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M5 5l1.8 1.8M17.2 17.2 19 19M19 5l-1.8 1.8M6.8 17.2 5 19',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z',
  logout: 'M15 5.5V4a1.5 1.5 0 0 0-1.5-1.5h-8A1.5 1.5 0 0 0 4 4v16a1.5 1.5 0 0 0 1.5 1.5h8A1.5 1.5 0 0 0 15 20v-1.5M10 12h11M21 12l-3.5-3.5M21 12l-3.5 3.5',
  key: 'M14 10a4 4 0 1 1 4 4h-1.5v2.5H14V19h-2.5v2.5H8.5V17L14 11.5A4 4 0 0 1 14 10Z',
  store: 'M4 9.5V20h16V9.5M2.5 9.5 5 4h14l2.5 5.5H2.5ZM9.5 20v-6h5v6',
  trendUp: 'M3 17 9.5 10.5 13.5 14.5 21 7M21 7h-5M21 7v5',
  trendDown: 'M3 7 9.5 13.5 13.5 9.5 21 17M21 17h-5M21 17v-5',
  file: 'M6 2.5h7L18 7.5V21.5H6V2.5ZM13 2.5V8h5',
  eye: 'M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  users: 'M9 11.5a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5ZM2.5 20.5c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5M16 4.4a3.75 3.75 0 0 1 0 7.2M17.5 15.4c2.4.6 4 2.4 4 5.1',
  mail: 'M3 6.5h18v11H3v-11ZM3.4 7 12 13l8.6-6',
  shield: 'M12 2.8 4.5 5.6v5.7c0 4.3 3 8.2 7.5 9.9 4.5-1.7 7.5-5.6 7.5-9.9V5.6L12 2.8ZM8.8 12l2.3 2.3 4.1-4.6',
  swap: 'M4 8.5h13M13.5 5 17 8.5 13.5 12M20 15.5H7M10.5 12 7 15.5 10.5 19',
}

const props = withDefaults(
  defineProps<{ name: keyof typeof PATHS | string; size?: number | string }>(),
  { size: 18 },
)

const path = computed(() => PATHS[props.name] ?? PATHS.info)
</script>

<template>
  <svg
    class="icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="path" />
  </svg>
</template>

<style scoped>
.icon {
  flex: none;
}
</style>
