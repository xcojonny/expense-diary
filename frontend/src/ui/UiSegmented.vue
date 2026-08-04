<script setup lang="ts">
/** Umschalter für wenige gleichrangige Ansichten (z. B. die Sortierung). */
export interface Segment {
  value: string
  label: string
}

defineProps<{ segments: Segment[]; ariaLabel?: string }>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <div class="segmented" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="segment in segments"
      :key="segment.value"
      type="button"
      role="tab"
      :aria-selected="model === segment.value"
      :class="['segmented__item', { 'segmented__item--active': model === segment.value }]"
      @click="model = segment.value"
    >
      {{ segment.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}

.segmented__item {
  padding: 5px 11px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 550;
  color: var(--text-muted);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--transition),
    color var(--transition);
}

.segmented__item:hover:not(.segmented__item--active) {
  color: var(--text);
}

.segmented__item--active {
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-sm);
}
</style>
