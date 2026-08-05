<script setup lang="ts">
/**
 * Linienchart mit Achsen, Raster und Hover — für den Preisverlauf.
 *
 * Der Hover läuft über unsichtbare Bänder pro Punkt statt über
 * Koordinatenrechnung an der Maus: robust, ohne `getBoundingClientRect`, und
 * funktioniert per Touch genauso.
 */
import { computed, ref } from 'vue'

export interface LinePoint {
  label: string
  /** Rohwert (Cent). */
  value: number
  /** Fertig formatiert für den Tooltip. */
  display: string
  meta?: string
}

const props = defineProps<{ points: LinePoint[]; formatTick: (value: number) => string }>()

const W = 640
const H = 240
const PAD = { top: 16, right: 14, bottom: 30, left: 58 }

const hovered = ref<number | null>(null)

const scale = computed(() => {
  const values = props.points.map((point) => point.value)
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  // Etwas Luft, und bei einer konstanten Reihe ein künstliches Fenster, damit
  // die Linie nicht auf der Achse klebt.
  const span = rawMax - rawMin
  const padding = span === 0 ? Math.max(1, Math.abs(rawMax) * 0.1) : span * 0.15
  const min = rawMin - padding
  const max = rawMax + padding

  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const count = props.points.length

  return {
    min,
    max,
    x: (index: number) => PAD.left + (count === 1 ? innerW / 2 : (index / (count - 1)) * innerW),
    y: (value: number) => PAD.top + innerH - ((value - min) / (max - min)) * innerH,
    bandWidth: count > 0 ? innerW / count : innerW,
  }
})

const ticks = computed(() => {
  const { min, max, y } = scale.value
  return [0, 0.5, 1].map((step) => {
    const value = min + (max - min) * step
    return { value, y: y(value), label: props.formatTick(value) }
  })
})

const coords = computed(() =>
  props.points.map((point, index) => ({
    ...point,
    index,
    cx: scale.value.x(index),
    cy: scale.value.y(point.value),
  })),
)

const linePath = computed(() =>
  coords.value.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.cx} ${point.cy}`).join(' '),
)

const areaPath = computed(() => {
  if (!coords.value.length) return ''
  const bottom = H - PAD.bottom
  const first = coords.value[0]
  const last = coords.value[coords.value.length - 1]
  return `${linePath.value} L${last.cx} ${bottom} L${first.cx} ${bottom} Z`
})

/** Erste, mittlere und letzte Beschriftung — mehr wird auf Mobil unlesbar. */
const xLabels = computed(() => {
  const all = coords.value
  if (all.length <= 3) return all
  const middle = all[Math.floor(all.length / 2)]
  return [all[0], middle, all[all.length - 1]]
})

const active = computed(() => (hovered.value === null ? null : coords.value[hovered.value] ?? null))
</script>

<template>
  <div class="line">
    <svg :viewBox="`0 0 ${W} ${H}`" class="line__svg" role="img" aria-label="Preisverlauf">
      <!-- Raster + Y-Achse -->
      <g>
        <template v-for="tick in ticks" :key="tick.value">
          <line
            :x1="PAD.left"
            :x2="W - PAD.right"
            :y1="tick.y"
            :y2="tick.y"
            stroke="var(--chart-grid)"
            stroke-width="1"
          />
          <text :x="PAD.left - 9" :y="tick.y + 4" class="line__tick num">{{ tick.label }}</text>
        </template>
      </g>

      <path :d="areaPath" fill="var(--accent)" opacity="0.1" />
      <path
        :d="linePath"
        fill="none"
        stroke="var(--accent)"
        stroke-width="2.2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />

      <circle
        v-for="point in coords"
        :key="`dot-${point.index}`"
        :cx="point.cx"
        :cy="point.cy"
        :r="hovered === point.index ? 5 : 3.2"
        fill="var(--surface)"
        stroke="var(--accent)"
        stroke-width="2"
      />

      <text
        v-for="point in xLabels"
        :key="`x-${point.index}`"
        :x="point.cx"
        :y="H - 9"
        class="line__tick line__tick--x"
      >
        {{ point.label }}
      </text>

      <!-- Unsichtbare Hover-Bänder -->
      <rect
        v-for="point in coords"
        :key="`band-${point.index}`"
        :x="point.cx - scale.bandWidth / 2"
        :y="PAD.top"
        :width="scale.bandWidth"
        :height="H - PAD.top - PAD.bottom"
        fill="transparent"
        @mouseenter="hovered = point.index"
        @mouseleave="hovered = null"
        @touchstart.passive="hovered = point.index"
      />

      <line
        v-if="active"
        :x1="active.cx"
        :x2="active.cx"
        :y1="PAD.top"
        :y2="H - PAD.bottom"
        stroke="var(--accent)"
        stroke-width="1"
        stroke-dasharray="3 3"
        opacity="0.6"
      />
    </svg>

    <p class="line__readout">
      <template v-if="active">
        <strong class="num">{{ active.display }}</strong>
        <span class="muted">{{ active.label }}</span>
        <span v-if="active.meta" class="subtle">{{ active.meta }}</span>
      </template>
      <span v-else class="subtle">Punkt antippen für Details</span>
    </p>
  </div>
</template>

<style scoped>
.line {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.line__svg {
  width: 100%;
  height: auto;
}

.line__tick {
  font-size: 11px;
  text-anchor: end;
  fill: var(--chart-axis);
}

.line__tick--x {
  text-anchor: middle;
}

.line__readout {
  display: flex;
  gap: 9px;
  align-items: baseline;
  min-height: 20px;
  font-size: 0.8125rem;
}
</style>
