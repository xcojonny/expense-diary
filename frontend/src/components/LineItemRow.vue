<script setup lang="ts">
/**
 * Eine editierbare Bon-Position.
 *
 * Beträge laufen über `UiMoneyInput`, dessen Modell **Cent** ist — es gibt an
 * dieser Stelle keinen Weg, versehentlich eine Fließkommazahl zu erzeugen
 * (ADR-003).
 */
import { computed, ref, watch } from 'vue'

import { formatCents, formatQuantityWithUnit, milliToInput, parseQuantityInput } from '@/lib/money'
import { useCategories } from '@/stores/categories'
import type { LineItem, LineKind } from '@/types/api'
import UiButton from '@/ui/UiButton.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'
import UiMoneyInput from '@/ui/UiMoneyInput.vue'
import UiSelect from '@/ui/UiSelect.vue'

export interface LineItemPatch {
  name?: string
  total_price_cents?: number
  quantity_milli?: number | null
  unit?: string | null
  category_id?: number | null
  clear_category?: boolean
  kind?: LineKind
}

const props = defineProps<{ item: LineItem; saving?: boolean }>()
const emit = defineEmits<{ save: [patch: LineItemPatch]; remove: [] }>()

const { options, nameFor } = useCategories()

const KIND_LABELS: Record<LineKind, string> = {
  product: 'Artikel',
  deposit: 'Pfand',
  discount: 'Rabatt',
}

const editing = ref(false)

const name = ref(props.item.name)
const totalCents = ref<number | null>(props.item.total_price_cents)
const quantityText = ref(milliToInput(props.item.quantity_milli))
const unit = ref(props.item.unit ?? '')
const categoryId = ref(props.item.category_id === null ? '' : String(props.item.category_id))
const kind = ref<LineKind>(props.item.kind)

// Von außen aktualisierte Werte übernehmen, solange nicht editiert wird.
watch(
  () => props.item,
  (item) => {
    if (editing.value) return
    name.value = item.name
    totalCents.value = item.total_price_cents
    quantityText.value = milliToInput(item.quantity_milli)
    unit.value = item.unit ?? ''
    categoryId.value = item.category_id === null ? '' : String(item.category_id)
    kind.value = item.kind
  },
)

const categoryOptions = computed(() =>
  options.value.map((option) => ({ value: String(option.id), label: option.label })),
)

const kindOptions = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }))

const categoryName = computed(() => nameFor(props.item.category_id))

function submit(): void {
  emit('save', {
    name: name.value.trim() || props.item.name,
    total_price_cents: totalCents.value ?? props.item.total_price_cents,
    quantity_milli: parseQuantityInput(quantityText.value),
    unit: unit.value.trim() || null,
    kind: kind.value,
    // `null` ist in JSON nicht von „weglassen" zu unterscheiden — deshalb das
    // ausdrückliche Flag.
    category_id: categoryId.value ? Number(categoryId.value) : undefined,
    clear_category: !categoryId.value,
  })
  editing.value = false
}

function cancel(): void {
  editing.value = false
  name.value = props.item.name
  totalCents.value = props.item.total_price_cents
}
</script>

<template>
  <li :class="['line', { 'line--editing': editing }]">
    <!-- Anzeige -->
    <template v-if="!editing">
      <button type="button" class="line__view" @click="editing = true">
        <span class="line__main">
          <span class="line__name">{{ item.name }}</span>
          <span class="line__meta">
            <template v-if="item.kind !== 'product'">
              {{ KIND_LABELS[item.kind] }} ·
            </template>
            <template v-if="item.quantity_milli">
              {{ formatQuantityWithUnit(item.quantity_milli, item.unit) }}
              <template v-if="item.unit_price_cents">
                × {{ formatCents(item.unit_price_cents) }}
              </template>
              ·
            </template>
            {{ categoryName ?? 'Ohne Kategorie' }}
          </span>
        </span>
        <span class="line__price num">{{ formatCents(item.total_price_cents) }}</span>
        <UiIcon name="edit" :size="15" class="line__edit-hint" />
      </button>
    </template>

    <!-- Bearbeiten -->
    <form v-else class="line__form" @submit.prevent="submit">
      <div class="line__grid">
        <label class="line__label line__label--wide">
          <span>Bezeichnung</span>
          <UiInput v-model="name" placeholder="Artikelname" />
        </label>
        <label class="line__label">
          <span>Menge</span>
          <UiInput v-model="quantityText" inputmode="decimal" align="right" numeric placeholder="1" />
        </label>
        <label class="line__label line__label--narrow">
          <span>Einheit</span>
          <UiInput v-model="unit" placeholder="stk" />
        </label>
        <label class="line__label">
          <span>Preis</span>
          <UiMoneyInput v-model="totalCents" />
        </label>
        <label class="line__label line__label--wide">
          <span>Kategorie</span>
          <UiSelect
            v-model="categoryId"
            :options="categoryOptions"
            placeholder="Ohne Kategorie"
          />
        </label>
        <label class="line__label">
          <span>Art</span>
          <UiSelect v-model="kind" :options="kindOptions" />
        </label>
      </div>

      <div class="line__buttons">
        <UiButton variant="danger" size="sm" icon="trash" @click="emit('remove')">Löschen</UiButton>
        <span class="line__spacer" />
        <UiButton variant="ghost" size="sm" @click="cancel">Abbrechen</UiButton>
        <UiButton variant="primary" size="sm" type="submit" :loading="saving">Speichern</UiButton>
      </div>
    </form>
  </li>
</template>

<style scoped>
.line {
  border-top: 1px solid var(--border);
}

.line--editing {
  background: var(--surface-muted);
}

.line__view {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 100%;
  padding: 10px 16px;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
}

.line__view:hover {
  background: var(--surface-hover);
}

.line__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.line__name {
  overflow: hidden;
  font-size: 0.875rem;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.line__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.line__price {
  flex: none;
  font-size: 0.875rem;
  font-weight: 560;
}

.line__edit-hint {
  flex: none;
  color: var(--text-subtle);
  opacity: 0;
  transition: opacity var(--transition);
}

.line__view:hover .line__edit-hint {
  opacity: 1;
}

.line__form {
  padding: 13px 16px;
}

.line__grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}

.line__label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  font-size: 0.75rem;
  font-weight: 550;
  color: var(--text-muted);
}

.line__label--wide {
  grid-column: span 2;
}

.line__label--narrow {
  max-width: 110px;
}

.line__buttons {
  display: flex;
  gap: 7px;
  align-items: center;
  margin-top: 12px;
}

.line__spacer {
  flex: 1;
}

@media (width <= 560px) {
  .line__label--wide {
    grid-column: span 2;
  }
}
</style>
