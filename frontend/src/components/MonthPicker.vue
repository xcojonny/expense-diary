<script setup lang="ts">
/** Monatsnavigation. „Weiter" endet beim laufenden Monat — in der Zukunft gibt
 *  es keine Bons, und ein leerer Bericht sieht wie ein Fehler aus. */
import { computed } from 'vue'

import { monthLabel } from '@/lib/format'
import UiButton from '@/ui/UiButton.vue'
import UiIcon from '@/ui/UiIcon.vue'

const year = defineModel<number>('year', { required: true })
const month = defineModel<number>('month', { required: true })

const now = new Date()

const isCurrent = computed(
  () => year.value === now.getFullYear() && month.value === now.getMonth() + 1,
)

function shift(delta: number): void {
  const date = new Date(year.value, month.value - 1 + delta, 1)
  year.value = date.getFullYear()
  month.value = date.getMonth() + 1
}

function jumpToCurrent(): void {
  year.value = now.getFullYear()
  month.value = now.getMonth() + 1
}
</script>

<template>
  <div class="picker">
    <UiButton variant="ghost" size="sm" aria-label="Vorheriger Monat" @click="shift(-1)">
      <UiIcon name="chevronLeft" :size="17" />
    </UiButton>
    <button type="button" class="picker__label" :disabled="isCurrent" @click="jumpToCurrent">
      {{ monthLabel(year, month) }}
    </button>
    <UiButton
      variant="ghost"
      size="sm"
      aria-label="Nächster Monat"
      :disabled="isCurrent"
      @click="shift(1)"
    >
      <UiIcon name="chevronRight" :size="17" />
    </UiButton>
  </div>
</template>

<style scoped>
.picker {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.picker__label {
  min-width: 9.5rem;
  padding: 5px 8px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 560;
  text-align: center;
  cursor: pointer;
}

.picker__label:disabled {
  cursor: default;
}

.picker__label:hover:not(:disabled) {
  background: var(--surface-hover);
}
</style>
