<script setup lang="ts">
/**
 * Donut mit Legende — für die Kategorienaufteilung eines Monats.
 *
 * Handgeschriebenes SVG (ADR-009): vier Diagrammtypen rechtfertigen keine
 * Chart-Bibliothek, und so nutzen sie dieselben Tokens wie der Rest der App.
 */
import { computed } from 'vue'

export interface DonutSlice {
  key: string | number
  label: string
  /** Fertig formatierter Betrag. */
  value: string
  /** Rohwert für den Winkel. */
  weight: number
}

const props = withDefaults(
  defineProps<{ slices: DonutSlice[]; centerLabel?: string; centerValue?: string; maxSlices?: number }>(),
  { maxSlices: 6 },
)

const RADIUS = 56
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/** Kleine Posten zu „Übrige" zusammenfassen — sonst wird der Ring zum Kamm. */
const grouped = computed<DonutSlice[]>(() => {
  const sorted = [...props.slices].sort((a, b) => b.weight - a.weight)
  if (sorted.length <= props.maxSlices) return sorted

  const head = sorted.slice(0, props.maxSlices - 1)
  const tail = sorted.slice(props.maxSlices - 1)
  const rest = tail.reduce((sum, slice) => sum + slice.weight, 0)
  return [...head, { key: '__rest', label: `Übrige (${tail.length})`, value: '', weight: rest }]
})

const total = computed(() => grouped.value.reduce((sum, slice) => sum + Math.max(0, slice.weight), 0))

const arcs = computed(() => {
  let offset = 0
  return grouped.value.map((slice, index) => {
    const fraction = total.value > 0 ? Math.max(0, slice.weight) / total.value : 0
    const arc = {
      ...slice,
      color: `var(--chart-${(index % 8) + 1})`,
      dash: `${fraction * CIRCUMFERENCE} ${CIRCUMFERENCE}`,
      dashOffset: -offset * CIRCUMFERENCE,
      percent: fraction,
    }
    offset += fraction
    return arc
  })
})

const percentText = (fraction: number): string =>
  `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(fraction * 100)} %`
</script>

<template>
  <div class="donut">
    <svg class="donut__svg" viewBox="0 0 140 140" role="img" :aria-label="centerLabel ?? 'Aufteilung'">
      <g transform="rotate(-90 70 70)">
        <circle cx="70" cy="70" :r="RADIUS" fill="none" stroke="var(--chart-grid)" stroke-width="15" />
        <circle
          v-for="arc in arcs"
          :key="arc.key"
          cx="70"
          cy="70"
          :r="RADIUS"
          fill="none"
          :stroke="arc.color"
          stroke-width="15"
          :stroke-dasharray="arc.dash"
          :stroke-dashoffset="arc.dashOffset"
          stroke-linecap="butt"
        />
      </g>
      <text v-if="centerValue" x="70" y="67" class="donut__value num">{{ centerValue }}</text>
      <text v-if="centerLabel" x="70" y="83" class="donut__caption">{{ centerLabel }}</text>
    </svg>

    <ul class="donut__legend">
      <li v-for="arc in arcs" :key="arc.key" class="donut__entry">
        <span class="donut__dot" :style="{ background: arc.color }" />
        <span class="donut__name">{{ arc.label }}</span>
        <span class="donut__share num">{{ percentText(arc.percent) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.donut {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  align-items: center;
}

.donut__svg {
  flex: none;
  width: 148px;
  height: 148px;
}

.donut__value {
  font-size: 15px;
  font-weight: 620;
  text-anchor: middle;
  fill: var(--text);
}

.donut__caption {
  font-size: 9px;
  text-anchor: middle;
  fill: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.donut__legend {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  min-width: 170px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.donut__entry {
  display: flex;
  gap: 9px;
  align-items: center;
  font-size: 0.8125rem;
}

.donut__dot {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 3px;
}

.donut__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.donut__share {
  flex: none;
  color: var(--text-muted);
}
</style>
