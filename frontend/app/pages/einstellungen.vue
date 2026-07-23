<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useApi } from '~/composables/useApi'

interface ApiToken {
  id: string
  name: string
  created_at: string
  last_used_at: string | null
}
interface ApiTokenCreated extends ApiToken {
  token: string
}

const { api } = useApi()

const tokens = ref<ApiToken[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const newName = ref('iOS Kurzbefehl')
const creating = ref(false)
const freshToken = ref<string | null>(null) // shown once, right after creation
const copied = ref(false)

// The exact endpoint the iOS Shortcut posts to (this instance's own origin).
const uploadUrl = computed(() =>
  typeof window !== 'undefined' ? `${window.location.origin}/api/v1/receipts` : '/api/v1/receipts',
)

async function load() {
  loading.value = true
  error.value = null
  try {
    tokens.value = await api<ApiToken[]>('/me/tokens')
  } catch {
    error.value = 'Tokens konnten nicht geladen werden.'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!newName.value.trim()) return
  creating.value = true
  error.value = null
  freshToken.value = null
  copied.value = false
  try {
    const created = await api<ApiTokenCreated>('/me/tokens', {
      method: 'POST',
      body: { name: newName.value.trim() },
    })
    freshToken.value = created.token
    newName.value = 'iOS Kurzbefehl'
    await load()
  } catch {
    error.value = 'Token konnte nicht erstellt werden.'
  } finally {
    creating.value = false
  }
}

async function revoke(id: string) {
  error.value = null
  try {
    await api(`/me/tokens/${id}`, { method: 'DELETE' })
    if (freshToken.value) freshToken.value = null
    await load()
  } catch {
    error.value = 'Token konnte nicht widerrufen werden.'
  }
}

async function copyToken() {
  if (!freshToken.value) return
  try {
    await navigator.clipboard.writeText(freshToken.value)
    copied.value = true
  } catch {
    copied.value = false
  }
}

function fmt(d: string | null): string {
  if (!d) return 'nie'
  return new Date(d).toLocaleString('de-DE')
}

onMounted(load)
</script>

<template>
  <div class="space-y-8">
    <section>
      <h1 class="text-xl font-semibold">Einstellungen</h1>
      <p class="mt-1 text-sm text-gray-500">Upload-Tokens für den iOS-Kurzbefehl.</p>
    </section>

    <p v-if="error" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>

    <!-- Create -->
    <section class="rounded border bg-white p-4">
      <h2 class="mb-1 font-medium">Neues Upload-Token</h2>
      <p class="mb-3 text-sm text-gray-500">
        Erzeugt einen dauerhaften Schlüssel, mit dem ein iOS-Kurzbefehl Bons hochladen kann.
        Das Token wird <strong>nur einmal</strong> angezeigt — kopiere es sofort.
      </p>
      <form class="flex flex-wrap items-center gap-2" @submit.prevent="create">
        <input
          v-model="newName"
          placeholder="Name, z. B. iPhone"
          class="min-w-48 flex-1 rounded border px-3 py-2 text-sm"
        >
        <button
          type="submit"
          :disabled="creating"
          class="rounded bg-green-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Token erstellen
        </button>
      </form>

      <div v-if="freshToken" class="mt-3 rounded border border-green-200 bg-green-50 p-3">
        <p class="mb-2 text-sm text-green-800">
          Token erstellt. Jetzt kopieren — es wird nicht erneut angezeigt:
        </p>
        <div class="flex items-center gap-2">
          <code class="flex-1 overflow-x-auto rounded bg-white px-2 py-1 text-xs">{{ freshToken }}</code>
          <button
            class="rounded border border-green-600 px-2 py-1 text-xs text-green-700"
            @click="copyToken"
          >
            {{ copied ? 'Kopiert ✓' : 'Kopieren' }}
          </button>
        </div>
      </div>
    </section>

    <!-- List -->
    <section class="rounded border bg-white p-4">
      <h2 class="mb-3 font-medium">Aktive Tokens</h2>
      <p v-if="loading" class="text-sm text-gray-500">Lädt …</p>
      <p v-else-if="!tokens.length" class="text-sm text-gray-500">Noch keine Tokens.</p>
      <ul v-else class="divide-y">
        <li v-for="t in tokens" :key="t.id" class="flex items-center justify-between py-2">
          <div>
            <p class="text-sm font-medium">{{ t.name }}</p>
            <p class="text-xs text-gray-500">
              erstellt {{ fmt(t.created_at) }} · zuletzt genutzt {{ fmt(t.last_used_at) }}
            </p>
          </div>
          <button class="text-sm text-red-600 hover:underline" @click="revoke(t.id)">
            Widerrufen
          </button>
        </li>
      </ul>
    </section>

    <!-- iOS Shortcut how-to -->
    <section class="rounded border bg-white p-4 text-sm text-gray-700">
      <h2 class="mb-2 font-medium">iOS-Kurzbefehl einrichten</h2>
      <ol class="list-decimal space-y-1 pl-5">
        <li>Kurzbefehle-App → neuer Kurzbefehl → in den Einstellungen „Bei Teilen-Menü anzeigen" aktivieren, Eingabe: <em>Bilder, PDFs</em>.</li>
        <li>Aktion „Inhalte von URL abrufen":</li>
      </ol>
      <div class="mt-2 space-y-1 rounded bg-gray-50 p-3 text-xs">
        <p><span class="text-gray-500">URL:</span> <code>{{ uploadUrl }}</code></p>
        <p><span class="text-gray-500">Methode:</span> <code>POST</code></p>
        <p><span class="text-gray-500">Header:</span> <code>Authorization: Bearer &lt;dein Token&gt;</code></p>
        <p><span class="text-gray-500">Body:</span> <code>Formular</code> → Feld <code>file</code> = Typ <em>Datei</em> = die Kurzbefehl-Eingabe</p>
      </div>
      <p class="mt-2">
        Danach in der Lidl-App den Bon als PDF teilen → deinen Kurzbefehl wählen. Der Bon landet
        im Haushaltsbuch und wird automatisch verarbeitet.
      </p>
    </section>
  </div>
</template>
