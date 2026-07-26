<script setup lang="ts">
import type { Receipt, ReceiptStatus } from '~/types/models'

const { api } = useApi()
const { receipt, polling, start } = useReceiptPolling()

const selected = ref<File | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

const STATUS_LABEL: Record<ReceiptStatus, string> = {
  uploaded: 'Hochgeladen',
  processing: 'Wird verarbeitet …',
  done: 'Fertig',
  needs_review: 'Prüfung nötig',
  failed: 'Fehlgeschlagen',
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  selected.value = input.files?.[0] ?? null
}

async function upload() {
  if (!selected.value) return
  busy.value = true
  error.value = null
  try {
    const form = new FormData()
    form.append('file', selected.value)
    const created = await api<Receipt>('/receipts', { method: 'POST', body: form })
    start(created.id) // poll the status until extraction finishes
  } catch {
    error.value = 'Upload fehlgeschlagen.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-xl font-semibold">Bon hochladen</h1>
    <p class="text-gray-600">
      Foto oder PDF eines Kassenbons hochladen — die Extraktion läuft asynchron,
      der Status aktualisiert sich per Polling.
    </p>

    <div class="flex items-center gap-3">
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp,application/pdf"
        class="text-sm"
        @change="onPick"
      >
      <button
        class="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        :disabled="!selected || busy"
        @click="upload"
      >
        Hochladen
      </button>
    </div>

    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

    <div v-if="receipt" class="rounded border bg-white p-4">
      <div class="flex items-center justify-between">
        <span class="font-medium">{{ receipt.store_name ?? 'Unbekannter Markt' }}</span>
        <span class="text-sm text-gray-500">
          {{ STATUS_LABEL[receipt.status] }}<span v-if="polling"> · aktualisiert …</span>
        </span>
      </div>

      <table v-if="receipt.line_items.length" class="mt-3 w-full text-sm">
        <thead class="text-left text-gray-500">
          <tr>
            <th class="py-1">Position</th>
            <th class="py-1 text-right">Menge</th>
            <th class="py-1 text-right">Preis</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="li in receipt.line_items" :key="li.id" class="border-t">
            <td class="py-1">{{ li.name }}</td>
            <td class="py-1 text-right">{{ li.quantity ?? '' }} {{ li.unit ?? '' }}</td>
            <td class="py-1 text-right">{{ li.total_price }} {{ receipt.currency }}</td>
          </tr>
        </tbody>
      </table>

      <p v-else-if="receipt.status === 'needs_review'" class="mt-3 text-sm text-amber-700">
        Keine Positionen erkannt — bitte manuell erfassen (kommt in Schritt 5).
      </p>
    </div>
  </section>
</template>
