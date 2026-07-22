<script setup lang="ts">
import { computed } from 'vue'
import type { TrendPoint } from '~/types/models'

const props = defineProps<{ points: TrendPoint[] }>()

const W = 320
const H = 120
const PAD = 24

// Dependency-free SVG line chart (keeps the PWA fully offline). Scales the
// unit-price series into the padded viewBox and draws a polyline + dots.
const view = computed(() => {
  const pts = props.points
  if (pts.length === 0) return null
  const prices = pts.map((p) => Number(p.unit_price))
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const span = max - min || 1
  const stepX = pts.length > 1 ? (W - 2 * PAD) / (pts.length - 1) : 0

  const coords = pts.map((p, i) => {
    const x = PAD + i * stepX
    const y = H - PAD - ((Number(p.unit_price) - min) / span) * (H - 2 * PAD)
    return { x, y, price: Number(p.unit_price), day: p.day }
  })
  return {
    coords,
    polyline: coords.map((c) => `${c.x},${c.y}`).join(' '),
    min,
    max,
    first: pts[0]!.day,
    last: pts[pts.length - 1]!.day,
  }
})
</script>

<template>
  <div v-if="view">
    <svg :viewBox="`0 0 ${W} ${H}`" class="w-full" role="img" aria-label="Preisverlauf">
      <polyline
        :points="view.polyline"
        fill="none"
        stroke="#16a34a"
        stroke-width="2"
      />
      <circle v-for="(c, i) in view.coords" :key="i" :cx="c.x" :cy="c.y" r="3" fill="#16a34a">
        <title>{{ c.day }}: {{ c.price.toFixed(2) }} €</title>
      </circle>
      <text :x="PAD" :y="H - 4" font-size="9" fill="#6b7280">{{ view.first }}</text>
      <text :x="W - PAD" :y="H - 4" font-size="9" fill="#6b7280" text-anchor="end">
        {{ view.last }}
      </text>
      <text :x="4" :y="PAD" font-size="9" fill="#6b7280">{{ view.max.toFixed(2) }}</text>
      <text :x="4" :y="H - PAD" font-size="9" fill="#6b7280">{{ view.min.toFixed(2) }}</text>
    </svg>
  </div>
  <p v-else class="text-sm text-gray-500">Kein Preisverlauf vorhanden.</p>
</template>
