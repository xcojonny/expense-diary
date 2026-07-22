<script setup lang="ts">
import type { Receipt, ReceiptStatus } from '~/types/models'

const { api } = useApi()
const { data: receipts, pending, error } = await useAsyncData('receipts', () =>
  api<Receipt[]>('/receipts'),
)

const STATUS_STYLE: Record<ReceiptStatus, string> = {
  uploaded: 'bg-gray-100 text-gray-700',
  processing: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  needs_review: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Dashboard</h1>
      <NuxtLink to="/upload" class="text-sm text-green-600 hover:underline">+ Bon hochladen</NuxtLink>
    </div>

    <p v-if="pending" class="text-gray-500">Lädt …</p>
    <p v-else-if="error" class="text-red-600">Bons konnten nicht geladen werden.</p>
    <p v-else-if="!receipts?.length" class="text-gray-600">
      Noch keine Bons. Lade den ersten hoch, um zu starten.
    </p>

    <ul v-else class="divide-y rounded border bg-white">
      <li v-for="r in receipts" :key="r.id">
        <NuxtLink
          :to="`/bon/${r.id}`"
          class="flex items-center justify-between p-3 hover:bg-gray-50"
        >
          <div>
            <div class="font-medium">{{ r.store_name ?? 'Unbekannter Markt' }}</div>
            <div class="text-xs text-gray-500">
              {{ r.purchased_at?.slice(0, 10) ?? r.created_at.slice(0, 10) }}
            </div>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="r.total" class="text-sm">{{ r.total }} {{ r.currency }}</span>
            <span class="rounded px-2 py-0.5 text-xs" :class="STATUS_STYLE[r.status]">
              {{ r.status }}
            </span>
          </div>
        </NuxtLink>
      </li>
    </ul>
  </section>
</template>
