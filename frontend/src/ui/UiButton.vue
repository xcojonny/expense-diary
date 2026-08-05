<script setup lang="ts">
import UiIcon from './UiIcon.vue'

withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    icon?: string
    type?: 'button' | 'submit'
    disabled?: boolean
    loading?: boolean
    block?: boolean
  }>(),
  { variant: 'secondary', size: 'md', type: 'button' },
)
</script>

<template>
  <button
    :type="type"
    :class="['btn', `btn--${variant}`, `btn--${size}`, { 'btn--block': block }]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="spinner" aria-hidden="true" />
    <UiIcon v-else-if="icon" :name="icon" :size="size === 'sm' ? 15 : 17" />
    <slot />
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-weight: 550;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--transition),
    border-color var(--transition),
    color var(--transition);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn--sm {
  padding: 5px 10px;
  font-size: 0.8125rem;
}

.btn--md {
  padding: 8px 14px;
  font-size: 0.875rem;
}

.btn--lg {
  padding: 11px 20px;
  font-size: 0.9375rem;
}

.btn--block {
  width: 100%;
}

.btn--primary {
  background: var(--accent);
  color: var(--accent-fg);
}

.btn--primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn--secondary {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--text);
}

.btn--secondary:hover:not(:disabled) {
  background: var(--surface-hover);
}

.btn--ghost {
  background: transparent;
  color: var(--text-muted);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text);
}

.btn--danger {
  background: transparent;
  border-color: var(--border-strong);
  color: var(--danger);
}

.btn--danger:hover:not(:disabled) {
  background: var(--danger-soft);
  border-color: var(--danger);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentcolor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 620ms linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
