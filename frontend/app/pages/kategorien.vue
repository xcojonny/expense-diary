<script setup lang="ts">
import { ref } from 'vue'
import type { Category } from '~/types/models'

const { api } = useApi()
const { data: categories, refresh } = await useAsyncData('categories-admin', () =>
  api<Category[]>('/categories'),
)

const error = ref<string | null>(null)
const newName = ref('')
const newParent = ref<string | null>(null)

// Local editable copies keyed by id, so each row saves independently.
const edits = ref<Record<string, { name: string; parent_id: string | null }>>({})
function editOf(c: Category) {
  if (!edits.value[c.id]) edits.value[c.id] = { name: c.name, parent_id: c.parent_id }
  return edits.value[c.id]!
}

async function call(fn: () => Promise<unknown>) {
  error.value = null
  try {
    await fn()
    edits.value = {}
    await refresh()
  } catch (e) {
    const detail = (e as { data?: { detail?: string } }).data?.detail
    error.value = detail ?? 'Aktion fehlgeschlagen.'
  }
}

function add() {
  if (!newName.value.trim()) return
  void call(async () => {
    await api('/categories', {
      method: 'POST',
      body: { name: newName.value.trim(), parent_id: newParent.value || null },
    })
    newName.value = ''
    newParent.value = null
  })
}

function save(c: Category) {
  const e = editOf(c)
  void call(() =>
    api(`/categories/${c.id}`, {
      method: 'PATCH',
      body: { name: e.name, parent_id: e.parent_id },
    }),
  )
}

function remove(c: Category) {
  void call(() => api(`/categories/${c.id}`, { method: 'DELETE' }))
}
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-xl font-semibold">Kategorien</h1>
    <p class="text-gray-600">
      Kategorien anlegen, umbenennen, verschachteln oder löschen. Beim Löschen
      werden Unterkategorien zu Hauptkategorien und betroffene Positionen ohne
      Kategorie geführt.
    </p>

    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- Add -->
    <div class="flex flex-wrap items-end gap-2 rounded border bg-white p-3">
      <label class="text-sm">
        <span class="text-gray-500">Neue Kategorie</span>
        <input v-model="newName" class="mt-1 block w-48 rounded border px-2 py-1" placeholder="Name">
      </label>
      <label class="text-sm">
        <span class="text-gray-500">Übergeordnet</span>
        <select v-model="newParent" class="mt-1 block w-48 rounded border px-2 py-1">
          <option :value="null">— (Hauptkategorie)</option>
          <option v-for="c in categories ?? []" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <button class="rounded bg-green-600 px-3 py-1.5 text-sm text-white" @click="add">
        Hinzufügen
      </button>
    </div>

    <!-- List / edit -->
    <div class="rounded border bg-white">
      <div
        v-for="c in categories ?? []"
        :key="c.id"
        class="flex flex-wrap items-center gap-2 border-b p-2 last:border-0"
        :class="{ 'pl-6': c.parent_id }"
      >
        <input v-model="editOf(c).name" class="w-40 rounded border px-2 py-1 text-sm">
        <select v-model="editOf(c).parent_id" class="w-40 rounded border px-2 py-1 text-sm">
          <option :value="null">— (Hauptkategorie)</option>
          <option
            v-for="p in (categories ?? []).filter((x) => x.id !== c.id)"
            :key="p.id"
            :value="p.id"
          >
            {{ p.name }}
          </option>
        </select>
        <button class="text-sm text-green-600 hover:underline" @click="save(c)">Speichern</button>
        <button class="text-sm text-red-600 hover:underline" @click="remove(c)">Löschen</button>
      </div>
    </div>
  </section>
</template>
