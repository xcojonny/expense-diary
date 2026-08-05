<script setup lang="ts">
/**
 * Kategorienverwaltung.
 *
 * `is_food` ist hier umschaltbar, weil es ein Feld ist und keine Namensliste im
 * Code (ADR-007): eine Umbenennung darf die Kennzahl „Anteil am
 * Lebensmittelbudget" nicht stillschweigend verfälschen.
 */
import { computed, onMounted, ref } from 'vue'

import { api, ApiError } from '@/lib/api'
import { toast } from '@/lib/toast'
import PageHeader from '@/components/PageHeader.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import { useCategories } from '@/stores/categories'
import type { Category } from '@/types/api'
import UiBadge from '@/ui/UiBadge.vue'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'
import UiModal from '@/ui/UiModal.vue'
import UiSelect from '@/ui/UiSelect.vue'

const { categories, options, ensureLoaded } = useCategories()

const loading = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)

const newName = ref('')
const newParent = ref('')
const newIsFood = ref(true)
const createError = ref<string | null>(null)

const editing = ref<Category | null>(null)
const editName = ref('')
const editParent = ref('')
const editIsFood = ref(true)
const editError = ref<string | null>(null)

const toDelete = ref<Category | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await ensureLoaded(true)
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : 'Laden fehlgeschlagen.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const parentOptions = computed(() =>
  options.value.map((option) => ({ value: String(option.id), label: option.label })),
)

/** Baum: Top-Level mit ihren Kindern darunter. */
const tree = computed(() => {
  const roots = categories.value
    .filter((category) => category.parent_id === null)
    .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'de'))
  return roots.map((root) => ({
    root,
    children: categories.value
      .filter((category) => category.parent_id === root.id)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'de')),
  }))
})

const orphans = computed(() =>
  categories.value.filter(
    (category) =>
      category.parent_id !== null &&
      !categories.value.some((parent) => parent.id === category.parent_id),
  ),
)

async function create(): Promise<void> {
  saving.value = true
  createError.value = null
  try {
    await api.post<Category>('/categories', {
      name: newName.value,
      parent_id: newParent.value ? Number(newParent.value) : null,
      is_food: newIsFood.value,
    })
    newName.value = ''
    newParent.value = ''
    await load()
    toast.success('Kategorie angelegt.')
  } catch (caught) {
    createError.value = caught instanceof ApiError ? caught.message : 'Anlegen fehlgeschlagen.'
  } finally {
    saving.value = false
  }
}

function startEdit(category: Category): void {
  editing.value = category
  editName.value = category.name
  editParent.value = category.parent_id === null ? '' : String(category.parent_id)
  editIsFood.value = category.is_food
  editError.value = null
}

async function saveEdit(): Promise<void> {
  if (!editing.value) return
  saving.value = true
  editError.value = null
  try {
    await api.patch<Category>(`/categories/${editing.value.id}`, {
      name: editName.value,
      parent_id: editParent.value ? Number(editParent.value) : undefined,
      clear_parent: !editParent.value,
      is_food: editIsFood.value,
    })
    editing.value = null
    await load()
    toast.success('Kategorie gespeichert.')
  } catch (caught) {
    editError.value = caught instanceof ApiError ? caught.message : 'Speichern fehlgeschlagen.'
  } finally {
    saving.value = false
  }
}

async function toggleFood(category: Category): Promise<void> {
  try {
    await api.patch<Category>(`/categories/${category.id}`, { is_food: !category.is_food })
    await load()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Ändern fehlgeschlagen.')
  }
}

async function remove(): Promise<void> {
  if (!toDelete.value) return
  try {
    await api.delete(`/categories/${toDelete.value.id}`)
    await load()
    toast.success('Kategorie gelöscht.')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Löschen fehlgeschlagen.')
  } finally {
    toDelete.value = null
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="Kategorien"
      subtitle="Bestimmen, wie der Bericht Ausgaben gruppiert — und was als Lebensmittel zählt."
    />

    <div class="stack">
      <!-- Anlegen -->
      <UiCard title="Neue Kategorie">
        <form class="create" @submit.prevent="create">
          <UiField v-slot="{ id }" label="Name" :error="createError">
            <UiInput :id="id" v-model="newName" placeholder="z. B. Feinkost" />
          </UiField>
          <UiField v-slot="{ id }" label="Übergeordnet">
            <UiSelect
              :id="id"
              v-model="newParent"
              :options="parentOptions"
              placeholder="Keine (Top-Level)"
            />
          </UiField>
          <label class="switch">
            <input v-model="newIsFood" type="checkbox">
            <span>Zählt als Lebensmittel</span>
          </label>
          <UiButton
            variant="primary"
            type="submit"
            :loading="saving"
            :disabled="!newName.trim()"
          >
            Anlegen
          </UiButton>
        </form>
      </UiCard>

      <!-- Baum -->
      <UiCard title="Kategorienbaum" flush>
        <div class="pad">
          <ResourceBoundary
            :loading="loading"
            :error="error"
            :empty="tree.length === 0"
            empty-title="Keine Kategorien"
            empty-icon="tag"
            @retry="load"
          >
            <ul class="tree">
              <template v-for="group in tree" :key="group.root.id">
                <li class="node">
                  <span class="node__name">{{ group.root.name }}</span>
                  <button
                    type="button"
                    class="node__food"
                    :title="
                      group.root.is_food
                        ? 'Zählt zum Lebensmittelbudget — zum Umschalten klicken'
                        : 'Zählt nicht zum Lebensmittelbudget — zum Umschalten klicken'
                    "
                    @click="toggleFood(group.root)"
                  >
                    <UiBadge :tone="group.root.is_food ? 'success' : 'neutral'">
                      {{ group.root.is_food ? 'Lebensmittel' : 'Sonstiges' }}
                    </UiBadge>
                  </button>
                  <span class="node__actions">
                    <UiButton variant="ghost" size="sm" @click="startEdit(group.root)">
                      <UiIcon name="edit" :size="15" />
                      <span class="sr-only">Bearbeiten</span>
                    </UiButton>
                    <UiButton variant="ghost" size="sm" @click="toDelete = group.root">
                      <UiIcon name="trash" :size="15" />
                      <span class="sr-only">Löschen</span>
                    </UiButton>
                  </span>
                </li>
                <li v-for="child in group.children" :key="child.id" class="node node--child">
                  <span class="node__name">
                    <UiIcon name="chevronRight" :size="13" class="node__arrow" />
                    {{ child.name }}
                  </span>
                  <button type="button" class="node__food" @click="toggleFood(child)">
                    <UiBadge :tone="child.is_food ? 'success' : 'neutral'">
                      {{ child.is_food ? 'Lebensmittel' : 'Sonstiges' }}
                    </UiBadge>
                  </button>
                  <span class="node__actions">
                    <UiButton variant="ghost" size="sm" @click="startEdit(child)">
                      <UiIcon name="edit" :size="15" />
                      <span class="sr-only">Bearbeiten</span>
                    </UiButton>
                    <UiButton variant="ghost" size="sm" @click="toDelete = child">
                      <UiIcon name="trash" :size="15" />
                      <span class="sr-only">Löschen</span>
                    </UiButton>
                  </span>
                </li>
              </template>
              <li v-for="orphan in orphans" :key="`orphan-${orphan.id}`" class="node">
                <span class="node__name">{{ orphan.name }}</span>
                <span class="subtle">verwaist</span>
              </li>
            </ul>
          </ResourceBoundary>
        </div>
      </UiCard>
    </div>

    <!-- Bearbeiten -->
    <UiModal
      v-if="editing"
      title="Kategorie bearbeiten"
      confirm-label="Speichern"
      @close="editing = null"
      @confirm="saveEdit"
    >
      <div class="stack-sm">
        <UiField v-slot="{ id }" label="Name" :error="editError">
          <UiInput :id="id" v-model="editName" />
        </UiField>
        <UiField
          v-slot="{ id }"
          label="Übergeordnet"
          hint="Leer lassen macht die Kategorie zur Top-Level-Kategorie."
        >
          <UiSelect
            :id="id"
            v-model="editParent"
            :options="parentOptions.filter((option) => option.value !== String(editing?.id))"
            placeholder="Keine (Top-Level)"
          />
        </UiField>
        <label class="switch">
          <input v-model="editIsFood" type="checkbox">
          <span>Zählt als Lebensmittel</span>
        </label>
      </div>
    </UiModal>

    <!-- Löschen -->
    <UiModal
      v-if="toDelete"
      title="Kategorie löschen?"
      confirm-label="Löschen"
      danger
      @close="toDelete = null"
      @confirm="remove"
    >
      „{{ toDelete.name }}“ wird entfernt. Positionen und Artikel bleiben erhalten und verlieren
      nur ihre Kategorie; Unterkategorien werden zu Top-Level-Kategorien. Es gehen keine
      Ausgaben verloren.
    </UiModal>
  </div>
</template>

<style scoped>
.create {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  align-items: end;
}

.switch {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 9px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  cursor: pointer;
}

.switch input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.pad :deep(.skeleton-group),
.pad :deep(.failure) {
  margin: 14px 16px;
}

.tree {
  padding: 0;
  margin: 0;
  list-style: none;
}

.node {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 12px 8px 16px;
}

.node + .node {
  border-top: 1px solid var(--border);
}

.node--child {
  padding-left: 30px;
  background: var(--surface-muted);
}

.node__name {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  font-size: 0.875rem;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node__arrow {
  color: var(--text-subtle);
}

.node__food {
  flex: none;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
}

.node__actions {
  display: flex;
  flex: none;
  gap: 2px;
}
</style>
