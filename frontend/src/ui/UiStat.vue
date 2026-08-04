<script setup lang="ts">
/**
 * Kennzahl-Kachel: Label, große Zahl, optionale Veränderung.
 *
 * Die Richtung ist semantisch — „mehr ausgegeben" ist warnend, „weniger" gut.
 * Deshalb `direction`, nicht „rot/grün".
 */
import UiIcon from './UiIcon.vue'

withDefaults(
  defineProps<{
    label: string
    value: string
    hint?: string
    delta?: string | null
    /** `up` = mehr Ausgaben, `down` = weniger. */
    direction?: 'up' | 'down' | null
    accent?: boolean
  }>(),
  { direction: null },
)
</script>

<template>
  <div :class="['stat', { 'stat--accent': accent }]">
    <p class="stat__label">{{ label }}</p>
    <p class="stat__value num">{{ value }}</p>
    <p v-if="delta" :class="['stat__delta', direction ? `stat__delta--${direction}` : '']">
      <UiIcon v-if="direction" :name="direction === 'up' ? 'trendUp' : 'trendDown'" :size="14" />
      {{ delta }}
    </p>
    <p v-else-if="hint" class="stat__hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.stat--accent {
  background: var(--accent-soft);
  border-color: transparent;
}

.stat__label {
  font-size: 0.75rem;
  font-weight: 550;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.045em;
}

.stat__value {
  font-size: 1.6rem;
  font-weight: 620;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.stat__delta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-muted);
}

.stat__delta--up {
  color: var(--trend-up);
}

.stat__delta--down {
  color: var(--trend-down);
}

.stat__hint {
  font-size: 0.8125rem;
  color: var(--text-subtle);
}

@media (width <= 560px) {
  .stat__value {
    font-size: 1.35rem;
  }
}
</style>
