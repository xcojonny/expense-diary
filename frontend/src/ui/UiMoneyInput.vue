<script setup lang="ts">
/**
 * Betragsfeld, dessen Modell **Cent** ist (ADR-003).
 *
 * Nach außen gibt es nie eine Euro-Fließkommazahl: der Nutzer tippt „1,09", das
 * Modell hält `109`. Beim Verlassen des Feldes wird die Anzeige normalisiert,
 * damit „1,9" nicht als „1,9 €" stehen bleibt, wenn 1,90 € gemeint war.
 */
import { ref, watch } from 'vue'

import { centsToInput, parseCentsInput } from '@/lib/money'
import UiInput from './UiInput.vue'

const props = defineProps<{ id?: string; placeholder?: string; disabled?: boolean }>()
const model = defineModel<number | null>({ default: null })

const text = ref(centsToInput(model.value))
const invalid = ref(false)

// Änderungen von außen (z. B. neu geladene Daten) übernehmen — aber nicht,
// solange die Eingabe denselben Wert bedeutet, sonst springt der Cursor.
watch(model, (value) => {
  if (parseCentsInput(text.value) !== value) text.value = centsToInput(value)
})

watch(text, (raw) => {
  if (!raw.trim()) {
    invalid.value = false
    model.value = null
    return
  }
  const cents = parseCentsInput(raw)
  invalid.value = cents === null
  if (cents !== null) model.value = cents
})

function normalizeOnBlur(): void {
  if (model.value !== null && !invalid.value) text.value = centsToInput(model.value)
}
</script>

<template>
  <div class="money">
    <UiInput
      :id="props.id"
      v-model="text"
      :placeholder="props.placeholder ?? '0,00'"
      :disabled="props.disabled"
      :invalid="invalid"
      inputmode="decimal"
      align="right"
      numeric
      @blur="normalizeOnBlur"
    />
    <span class="money__unit" aria-hidden="true">€</span>
  </div>
</template>

<style scoped>
.money {
  position: relative;
  min-width: 0;
}

.money :deep(.input) {
  padding-right: 26px;
}

.money__unit {
  position: absolute;
  top: 50%;
  right: 10px;
  font-size: 0.8125rem;
  color: var(--text-subtle);
  pointer-events: none;
  transform: translateY(-50%);
}
</style>
