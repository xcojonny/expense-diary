<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ label: string; hint?: string; error?: string | null }>()

// Ein Label braucht ein Ziel — die ID kommt von hier und geht per Slot-Prop an
// das Eingabefeld.
const id = useId()
</script>

<template>
  <div class="field">
    <label class="field__label" :for="id">{{ label }}</label>
    <slot :id="id" />
    <p v-if="error" class="field__error">{{ error }}</p>
    <p v-else-if="hint" class="field__hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.field__label {
  font-size: 0.8125rem;
  font-weight: 550;
  color: var(--text-muted);
}

.field__hint {
  font-size: 0.75rem;
  color: var(--text-subtle);
}

.field__error {
  font-size: 0.75rem;
  color: var(--danger);
}
</style>
