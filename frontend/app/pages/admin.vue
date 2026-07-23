<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useApi } from '~/composables/useApi'

interface LogEntry {
  timestamp: string | null
  level: string
  event: string
  logger: string | null
  context: Record<string, string>
}

const { api } = useApi()

const entries = ref<LogEntry[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const level = ref('') // '' = all
const auto = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

// Newest first for reading.
const rows = computed(() => [...entries.value].reverse())

async function load() {
  error.value = null
  try {
    const query = level.value ? `?limit=500&level=${level.value}` : '?limit=500'
    entries.value = await api<LogEntry[]>(`/admin/logs${query}`)
  } catch (e) {
    error.value =
      (e as { status?: number })?.status === 403
        ? 'Nur Instanz-Admins dürfen die Logs sehen.'
        : 'Logs konnten nicht geladen werden.'
  } finally {
    loading.value = false
  }
}

function toggleAuto() {
  auto.value = !auto.value
  if (auto.value) timer = setInterval(load, 5000)
  else if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function badgeClass(lvl: string): string {
  const l = lvl.toLowerCase()
  if (l === 'error' || l === 'critical') return 'bg-red-100 text-red-700'
  if (l === 'warning' || l === 'warn') return 'bg-amber-100 text-amber-800'
  return 'bg-gray-100 text-gray-600'
}

function ctx(entry: LogEntry): string {
  return Object.entries(entry.context)
    .map(([k, v]) => `${k}=${v}`)
    .join('  ')
}

function fmt(ts: string | null): string {
  if (!ts) return ''
  return new Date(ts).toLocaleString('de-DE')
}

onMounted(load)
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-xl font-semibold">Logs</h1>
      <span class="text-sm text-gray-500">Backend-Prozess, seit letztem Neustart</span>
      <div class="ml-auto flex items-center gap-2">
        <select v-model="level" class="rounded border px-2 py-1 text-sm" @change="load">
          <option value="">Alle</option>
          <option value="info">Info+</option>
          <option value="warning">Warnung+</option>
          <option value="error">Fehler+</option>
        </select>
        <button
          class="rounded border px-2 py-1 text-sm"
          :class="auto ? 'border-green-600 text-green-700' : 'text-gray-600'"
          @click="toggleAuto"
        >
          Auto {{ auto ? 'an' : 'aus' }}
        </button>
        <button class="rounded bg-green-600 px-3 py-1 text-sm font-medium text-white" @click="load">
          Aktualisieren
        </button>
      </div>
    </div>

    <p v-if="error" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
    <p v-else-if="loading" class="text-sm text-gray-500">Lädt …</p>
    <p v-else-if="!rows.length" class="text-sm text-gray-500">Keine Log-Einträge.</p>

    <div v-else class="overflow-x-auto rounded border bg-white">
      <table class="w-full text-left text-xs">
        <thead class="border-b bg-gray-50 text-gray-500">
          <tr>
            <th class="px-3 py-2 font-medium">Zeit</th>
            <th class="px-3 py-2 font-medium">Level</th>
            <th class="px-3 py-2 font-medium">Ereignis</th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr v-for="(row, i) in rows" :key="i" class="align-top">
            <td class="whitespace-nowrap px-3 py-2 text-gray-500">{{ fmt(row.timestamp) }}</td>
            <td class="px-3 py-2">
              <span class="rounded px-1.5 py-0.5 font-medium uppercase" :class="badgeClass(row.level)">
                {{ row.level }}
              </span>
            </td>
            <td class="px-3 py-2">
              <span class="font-medium text-gray-800">{{ row.event }}</span>
              <span v-if="ctx(row)" class="ml-2 break-all text-gray-500">{{ ctx(row) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
