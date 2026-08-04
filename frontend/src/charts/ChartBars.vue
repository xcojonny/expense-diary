<script setup lang="ts">
/**
 * Rangliste mit Balken — das Arbeitspferd der Auswertung.
 *
 * Der Balken liegt hinter der Zeile, nicht daneben: dadurch bleibt die volle
 * Breite für Name und Betrag, und das Verhältnis ist trotzdem sofort sichtbar.
 */
import { computed } from 'vue'

export interface BarRow {
  key: string | number
  label: string
  /** Fertig formatiert — Formatierung passiert im Aufrufer, nie im Chart. */
  value: string
  /** Zweitzeile, z. B. „3× · 0,78 kg". */
  meta?: string
  /** Rohwert nur für die Balkenbreite. */
  weight: number
  /** Index in die Chart-Palette; ohne Angabe alle in Akzentfarbe. */
  colorIndex?: number
  clickable?: boolean
  active?: boolean
}

const props = withDefaults(defineProps<{ rows: BarRow[]; colorful?: boolean }>(), {
  colorful: false,
})
const emit = defineEmits<{ select: [row: BarRow] }>()

const max = computed(() => Math.max(1, ...props.rows.map((row) => Math.abs(row.weight))))

function width(row: BarRow): string {
  // Mindestens 2 %, damit auch winzige Posten sichtbar bleiben.
  return `${Math.max(2, (Math.abs(row.weight) / max.value) * 100)}%`
}

function color(row: BarRow): string {
  if (!props.colorful) return 'var(--accent)'
  return `var(--chart-${((row.colorIndex ?? 0) % 8) + 1})`
}
</script>

<template>
  <ul class="bars">
    <li v-for="row in rows" :key="row.key" class="bars__item">
      <component
        :is="row.clickable ? 'button' : 'div'"
        :type="row.clickable ? 'button' : undefined"
        :class="['bars__row', { 'bars__row--clickable': row.clickable, 'bars__row--active': row.active }]"
        @click="row.clickable && emit('select', row)"
      >
        <span class="bars__fill" :style="{ width: width(row), background: color(row) }" />
        <span class="bars__content">
          <span class="bars__label">
            <span class="bars__name">{{ row.label }}</span>
            <span v-if="row.meta" class="bars__meta">{{ row.meta }}</span>
          </span>
          <span class="bars__value num">{{ row.value }}</span>
        </span>
      </component>
    </li>
  </ul>
</template>

<style scoped>
.bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.bars__row {
  position: relative;
  display: block;
  width: 100%;
  padding: 9px 11px;
  overflow: hidden;
  text-align: left;
  background: var(--surface-muted);
  border: none;
  border-radius: var(--radius-sm);
  font: inherit;
  color: inherit;
}

.bars__row--clickable {
  cursor: pointer;
}

.bars__row--clickable:hover .bars__fill {
  opacity: 0.36;
}

.bars__row--active {
  box-shadow: inset 0 0 0 1.5px var(--accent);
}

.bars__fill {
  position: absolute;
  inset: 0 auto 0 0;
  opacity: 0.22;
  transition:
    width var(--transition),
    opacity var(--transition);
}

.bars__content {
  position: relative;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.bars__label {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.bars__name {
  overflow: hidden;
  font-size: 0.875rem;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bars__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.bars__value {
  flex: none;
  font-size: 0.875rem;
  font-weight: 560;
}
</style>
