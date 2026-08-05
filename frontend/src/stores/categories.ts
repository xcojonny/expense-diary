/**
 * Kategorien — einmal laden, überall verwenden.
 *
 * Bon-Detail, Bericht und Kategorienverwaltung brauchen alle dieselbe Liste;
 * ein gemeinsamer Cache spart Anfragen und hält die Auswahlfelder konsistent.
 */

import { computed, ref } from 'vue'

import { api } from '@/lib/api'
import type { Category } from '@/types/api'

const items = ref<Category[]>([])
const loading = ref(false)
let loaded = false

export interface CategoryOption {
  id: number
  /** Mit Elternteil-Präfix: „Milchprodukte & Eier › Käse". */
  label: string
  depth: number
  is_food: boolean
}

function buildOptions(all: Category[]): CategoryOption[] {
  const byParent = new Map<number | null, Category[]>()
  for (const category of all) {
    const bucket = byParent.get(category.parent_id) ?? []
    bucket.push(category)
    byParent.set(category.parent_id, bucket)
  }
  for (const bucket of byParent.values()) {
    bucket.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'de'))
  }

  const options: CategoryOption[] = []
  const walk = (parentId: number | null, depth: number, prefix: string): void => {
    for (const category of byParent.get(parentId) ?? []) {
      const label = prefix ? `${prefix} › ${category.name}` : category.name
      options.push({ id: category.id, label, depth, is_food: category.is_food })
      walk(category.id, depth + 1, label)
    }
  }
  walk(null, 0, '')
  return options
}

export const useCategories = () => ({
  categories: computed(() => items.value),
  options: computed(() => buildOptions(items.value)),
  loading: computed(() => loading.value),

  nameFor(id: number | null | undefined): string | null {
    if (id === null || id === undefined) return null
    return items.value.find((category) => category.id === id)?.name ?? null
  },

  /** Lädt beim ersten Aufruf; `force` erzwingt ein Neuladen nach Änderungen. */
  async ensureLoaded(force = false): Promise<void> {
    if (loaded && !force) return
    loading.value = true
    try {
      items.value = await api.get<Category[]>('/categories')
      loaded = true
    } finally {
      loading.value = false
    }
  },
})
