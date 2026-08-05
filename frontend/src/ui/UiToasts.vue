<script setup lang="ts">
import { dismiss, toasts } from '@/lib/toast'
import UiIcon from './UiIcon.vue'

const ICONS = { success: 'check', error: 'warning', info: 'info' } as const
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <button
        v-for="item in toasts"
        :key="item.id"
        type="button"
        :class="['toast', `toast--${item.tone}`]"
        @click="dismiss(item.id)"
      >
        <UiIcon :name="ICONS[item.tone]" :size="16" />
        <span>{{ item.text }}</span>
      </button>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 14px;
  bottom: calc(var(--bottom-nav-height) + 14px);
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
  pointer-events: none;
}

@media (width >= 900px) {
  .toasts {
    bottom: 18px;
  }
}

.toast {
  display: flex;
  align-items: center;
  gap: 9px;
  max-width: min(88vw, 400px);
  padding: 10px 14px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  font-size: 0.8125rem;
  cursor: pointer;
  pointer-events: auto;
}

.toast--success {
  border-left-color: var(--success);
  color: var(--success);
}

.toast--error {
  border-left-color: var(--danger);
  color: var(--danger);
}

.toast--info {
  border-left-color: var(--info);
  color: var(--info);
}

.toast span {
  color: var(--text);
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--transition),
    transform var(--transition);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(14px);
}
</style>
