<script setup lang="ts">
import UiIcon from './UiIcon.vue'

export interface SelectOption {
  value: string
  label: string
}

withDefaults(
  defineProps<{
    id?: string
    options: SelectOption[]
    placeholder?: string
    disabled?: boolean
  }>(),
  {},
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <div class="select">
    <select :id="id" v-model="model" :disabled="disabled" class="select__control">
      <option v-if="placeholder" value="">{{ placeholder }}</option>
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
    <UiIcon name="chevronDown" :size="15" class="select__arrow" />
  </div>
</template>

<style scoped>
.select {
  position: relative;
  min-width: 0;
}

.select__control {
  width: 100%;
  padding: 8px 30px 8px 11px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  appearance: none;
  cursor: pointer;
  transition:
    border-color var(--transition),
    box-shadow var(--transition);
}

.select__control:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}

.select__control:disabled {
  background: var(--surface-muted);
  color: var(--text-muted);
  cursor: not-allowed;
}

.select__arrow {
  position: absolute;
  top: 50%;
  right: 10px;
  color: var(--text-subtle);
  pointer-events: none;
  transform: translateY(-50%);
}
</style>
