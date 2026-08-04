<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import UiButton from './UiButton.vue'
import UiIcon from './UiIcon.vue'

const props = defineProps<{ title: string; confirmLabel?: string; danger?: boolean }>()
const emit = defineEmits<{ close: []; confirm: [] }>()

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="overlay" role="dialog" aria-modal="true" :aria-label="title" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h2>{{ title }}</h2>
        <UiButton variant="ghost" size="sm" aria-label="Schließen" @click="emit('close')">
          <UiIcon name="x" :size="16" />
        </UiButton>
      </header>
      <div class="dialog__body">
        <slot />
      </div>
      <footer class="dialog__foot">
        <UiButton variant="ghost" @click="emit('close')">Abbrechen</UiButton>
        <UiButton
          :variant="props.danger ? 'danger' : 'primary'"
          @click="emit('confirm')"
        >
          {{ props.confirmLabel ?? 'Bestätigen' }}
        </UiButton>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 18px;
  background: var(--overlay);
  backdrop-filter: blur(2px);
}

.dialog {
  width: 100%;
  max-width: 420px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 12px 14px 18px;
  border-bottom: 1px solid var(--border);
}

.dialog__body {
  padding: 18px;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.dialog__foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 14px;
  background: var(--surface-muted);
  border-top: 1px solid var(--border);
}
</style>
