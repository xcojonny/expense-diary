<script setup lang="ts">
withDefaults(
  defineProps<{
    id?: string
    type?: string
    placeholder?: string
    disabled?: boolean
    invalid?: boolean
    align?: 'left' | 'right'
    inputmode?: 'text' | 'decimal' | 'numeric'
    /** Beträge und Mengen brauchen Tabellenziffern. */
    numeric?: boolean
    autocomplete?: string
  }>(),
  { type: 'text', align: 'left' },
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <input
    :id="id"
    v-model="model"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    :inputmode="inputmode"
    :autocomplete="autocomplete"
    :aria-invalid="invalid || undefined"
    :class="['input', `input--${align}`, { 'input--invalid': invalid, num: numeric }]"
  >
</template>

<style scoped>
.input {
  width: 100%;
  min-width: 0;
  padding: 8px 11px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  transition:
    border-color var(--transition),
    box-shadow var(--transition);
}

.input--right {
  text-align: right;
}

.input::placeholder {
  color: var(--text-subtle);
}

.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}

.input:disabled {
  background: var(--surface-muted);
  color: var(--text-muted);
  cursor: not-allowed;
}

.input--invalid {
  border-color: var(--danger);
}
</style>
