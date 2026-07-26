<script setup lang="ts">
import { computed } from 'vue'
import type { Comparison, MonthlyReport, Receipt, ReceiptStatus } from '~/types/models'

const { api } = useApi()

const { data, pending, error } = await useAsyncData('dashboard', () =>
  Promise.all([
    api<Receipt[]>('/receipts'),
    api<MonthlyReport>('/analytics/monthly'),
    api<Comparison>('/analytics/compare'),
  ]).then(([receipts, monthly, comparison]) => ({ receipts, monthly, comparison })),
)

const STATUS: Record<ReceiptStatus, { label: string, cls: string }> = {
  uploaded: { label: 'Hochgeladen', cls: 'bg-gray-100 text-gray-600' },
  processing: { label: 'Wird verarbeitet', cls: 'bg-blue-100 text-blue-700' },
  done: { label: 'Fertig', cls: 'bg-green-100 text-green-700' },
  needs_review: { label: 'Prüfen', cls: 'bg-amber-100 text-amber-800' },
  failed: { label: 'Fehler', cls: 'bg-red-100 text-red-700' },
}

const num = (v: string | null | undefined) => {
  const n = parseFloat(String(v ?? '').replace(',', '.'))
  return Number.isNaN(n) ? 0 : n
}
const eur = (v: string | number | null | undefined) =>
  num(typeof v === 'number' ? String(v) : v).toLocaleString('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + ' €'

const hasReceipts = computed(() => (data.value?.receipts.length ?? 0) > 0)

const monthLabel = computed(() =>
  data.value
    ? new Date(data.value.monthly.year, data.value.monthly.month - 1, 1).toLocaleDateString(
      'de-DE',
      { month: 'long', year: 'numeric' },
    )
    : '',
)

// Month-over-month trend for the headline number.
const trend = computed(() => {
  const c = data.value?.comparison
  if (!c || num(c.previous_total) === 0 || c.delta_pct === null) return null
  const delta = num(c.delta)
  const pct = Math.abs(num(c.delta_pct))
  return {
    up: delta > 0,
    text: `${delta > 0 ? '▲' : '▼'} ${pct.toLocaleString('de-DE', { maximumFractionDigits: 1 })} % ${
      delta > 0 ? 'mehr' : 'weniger'
    } als im Vormonat`,
  }
})

const topCats = computed(() => (data.value?.monthly.by_category ?? []).slice(0, 5))
const maxCat = computed(() => Math.max(1, ...topCats.value.map(c => num(c.total))))

// Most recent receipts first (backend already orders desc); cap the list.
const recent = computed(() => (data.value?.receipts ?? []).slice(0, 10))
</script>

<template>
  <section class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold">Dashboard</h1>
        <p class="text-sm text-gray-500">{{ monthLabel }}</p>
      </div>
      <NuxtLink to="/upload" class="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white">
        + Bon hochladen
      </NuxtLink>
    </div>

    <p v-if="pending" class="text-gray-500">Lädt …</p>
    <p v-else-if="error" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
      Daten konnten nicht geladen werden.
    </p>

    <template v-else-if="!hasReceipts">
      <div class="rounded-lg border bg-white p-8 text-center">
        <p class="text-gray-600">Noch keine Bons.</p>
        <NuxtLink to="/upload" class="mt-2 inline-block text-sm text-green-600 hover:underline">
          Lade den ersten hoch, um zu starten →
        </NuxtLink>
      </div>
    </template>

    <template v-else-if="data">
      <!-- Stat cards -->
      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-lg border bg-white p-4 shadow-sm sm:col-span-1">
          <p class="text-xs uppercase tracking-wide text-gray-400">Ausgaben {{ monthLabel }}</p>
          <p class="mt-1 text-3xl font-semibold">{{ eur(data.monthly.total_spending) }}</p>
          <p
            v-if="trend"
            class="mt-1 text-xs"
            :class="trend.up ? 'text-amber-600' : 'text-green-600'"
          >
            {{ trend.text }}
          </p>
          <p v-else class="mt-1 text-xs text-gray-400">kein Vormonatsvergleich</p>
        </div>
        <div class="rounded-lg border bg-white p-4 shadow-sm">
          <p class="text-xs uppercase tracking-wide text-gray-400">Bons diesen Monat</p>
          <p class="mt-1 text-3xl font-semibold">{{ data.monthly.receipt_count }}</p>
          <p class="mt-1 text-xs text-gray-400">Pfand {{ eur(data.monthly.deposit_total) }}</p>
        </div>
        <div class="rounded-lg border bg-white p-4 shadow-sm">
          <p class="text-xs uppercase tracking-wide text-gray-400">Ersparnis (Rabatte)</p>
          <p class="mt-1 text-3xl font-semibold">{{ eur(data.monthly.discount_total) }}</p>
          <NuxtLink to="/bericht" class="mt-1 inline-block text-xs text-green-600 hover:underline">
            Zum Bericht →
          </NuxtLink>
        </div>
      </div>

      <!-- Top categories -->
      <div v-if="topCats.length" class="rounded-lg border bg-white p-4 shadow-sm">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-medium">Top-Kategorien</h2>
          <NuxtLink to="/bericht" class="text-xs text-green-600 hover:underline">Details</NuxtLink>
        </div>
        <ul class="space-y-2">
          <li v-for="c in topCats" :key="c.category_id ?? c.category_name">
            <div class="mb-0.5 flex justify-between text-sm">
              <span>{{ c.category_name }}</span>
              <span class="text-gray-600">{{ eur(c.total) }}</span>
            </div>
            <div class="h-2 rounded bg-gray-100">
              <div
                class="h-2 rounded bg-green-500"
                :style="{ width: `${Math.max(3, (num(c.total) / maxCat) * 100)}%` }"
              />
            </div>
          </li>
        </ul>
      </div>

      <!-- Recent receipts -->
      <div class="rounded-lg border bg-white shadow-sm">
        <h2 class="border-b p-3 font-medium">Letzte Bons</h2>
        <ul class="divide-y">
          <li v-for="r in recent" :key="r.id">
            <NuxtLink :to="`/bon/${r.id}`" class="flex items-center justify-between p-3 hover:bg-gray-50">
              <div class="min-w-0">
                <div class="truncate font-medium">{{ r.store_name ?? 'Unbekannter Markt' }}</div>
                <div class="text-xs text-gray-500">
                  {{ (r.purchased_at ?? r.created_at).slice(0, 10) }}
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-3">
                <span v-if="r.total" class="text-sm font-medium">{{ eur(r.total) }}</span>
                <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="STATUS[r.status].cls">
                  {{ STATUS[r.status].label }}
                </span>
              </div>
            </NuxtLink>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>
