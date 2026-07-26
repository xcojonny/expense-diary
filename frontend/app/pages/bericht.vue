<script setup lang="ts">
import { computed, ref } from 'vue'
import type {
  Comparison,
  ExpensiveItemsReport,
  ItemUsage,
  MonthlyReport,
  TrendPoint,
} from '~/types/models'

const { api } = useApi()
const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)

// Price trend on demand when the user picks an item.
const selectedItem = ref<{ id: string; name: string } | null>(null)
const trend = ref<TrendPoint[]>([])

function shift(delta: number) {
  const d = new Date(year.value, month.value - 1 + delta, 1)
  year.value = d.getFullYear()
  month.value = d.getMonth() + 1
  selectedItem.value = null
}

const { data } = await useAsyncData(
  'bericht',
  () => {
    const q = `year=${year.value}&month=${month.value}`
    return Promise.all([
      api<MonthlyReport>(`/analytics/monthly?${q}`),
      api<Comparison>(`/analytics/compare?${q}`),
      api<ExpensiveItemsReport>(`/analytics/expensive?${q}`),
      api<ItemUsage[]>(`/analytics/overbought?${q}`),
    ]).then(([report, comparison, expensive, overbought]) => ({
      report,
      comparison,
      expensive,
      overbought,
    }))
  },
  { watch: [year, month] },
)

const maxCategory = computed(() =>
  Math.max(1, ...(data.value?.report.by_category ?? []).map((c) => Number(c.total))),
)

async function selectItem(id: string | null, name: string) {
  if (!id) return
  selectedItem.value = { id, name }
  trend.value = await api<TrendPoint[]>(`/analytics/price-trend/${id}`)
}
</script>

<template>
  <section v-if="data" class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Bericht</h1>
      <div class="flex items-center gap-2 text-sm">
        <button class="rounded border px-2 py-1" @click="shift(-1)">‹</button>
        <span class="w-32 text-center font-medium">{{ monthName(month) }} {{ year }}</span>
        <button class="rounded border px-2 py-1" @click="shift(1)">›</button>
      </div>
    </div>

    <!-- Summary + comparison -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded border bg-white p-3">
        <div class="text-xs text-gray-500">Gesamtausgaben</div>
        <div class="text-lg font-semibold">{{ eur(data.report.total_spending) }}</div>
        <div
          v-if="data.comparison.delta_pct !== null"
          class="text-xs"
          :class="Number(data.comparison.delta) > 0 ? 'text-red-600' : 'text-green-600'"
        >
          {{ pct(data.comparison.delta_pct) }} ggü. Vormonat
        </div>
      </div>
      <div class="rounded border bg-white p-3">
        <div class="text-xs text-gray-500">Bons</div>
        <div class="text-lg font-semibold">{{ data.report.receipt_count }}</div>
      </div>
      <div class="rounded border bg-white p-3">
        <div class="text-xs text-gray-500">Pfand</div>
        <div class="text-lg font-semibold">{{ eur(data.report.deposit_total) }}</div>
      </div>
      <div class="rounded border bg-white p-3">
        <div class="text-xs text-gray-500">Rabatte</div>
        <div class="text-lg font-semibold">{{ eur(data.report.discount_total) }}</div>
      </div>
    </div>

    <div v-if="!data.report.receipt_count" class="rounded border bg-white p-4 text-gray-600">
      Keine Bons in diesem Monat.
    </div>

    <template v-else>
      <!-- Category breakdown -->
      <div class="rounded border bg-white p-4">
        <h2 class="mb-3 font-medium">Ausgaben nach Kategorie</h2>
        <div v-for="c in data.report.by_category" :key="c.category_name" class="mb-2">
          <div class="flex justify-between text-sm">
            <span>{{ c.category_name }}</span>
            <span class="text-gray-600">{{ eur(c.total) }}</span>
          </div>
          <div class="mt-0.5 h-2 rounded bg-gray-100">
            <div
              class="h-2 rounded bg-green-500"
              :style="{ width: `${(Number(c.total) / maxCategory) * 100}%` }"
            />
          </div>
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <!-- Stores -->
        <div class="rounded border bg-white p-4">
          <h2 class="mb-3 font-medium">Ausgaben pro Markt</h2>
          <div
            v-for="s in data.report.by_store"
            :key="s.store_name"
            class="flex justify-between border-b py-1 text-sm last:border-0"
          >
            <span>{{ s.store_name }}</span>
            <span class="text-gray-600">{{ eur(s.total) }}</span>
          </div>
        </div>

        <!-- Top expensive single positions -->
        <div class="rounded border bg-white p-4">
          <h2 class="mb-3 font-medium">Teuerste Einzelpositionen</h2>
          <div
            v-for="(t, i) in data.report.top_items"
            :key="i"
            class="flex justify-between border-b py-1 text-sm last:border-0"
          >
            <span>{{ t.name }}</span>
            <span class="text-gray-600">{{ eur(t.total_price) }}</span>
          </div>
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <!-- Overbought -->
        <div class="rounded border bg-white p-4">
          <h2 class="mb-3 font-medium">Was kaufe ich am häufigsten</h2>
          <div
            v-for="u in data.overbought"
            :key="u.name"
            class="flex items-center justify-between border-b py-1 text-sm last:border-0"
          >
            <button class="text-left hover:text-green-600" @click="selectItem(u.item_id, u.name)">
              {{ u.name }}
            </button>
            <span class="text-gray-600">{{ u.count }}× · {{ eur(u.total_spend) }}</span>
          </div>
        </div>

        <!-- Expensive food with budget share -->
        <div class="rounded border bg-white p-4">
          <h2 class="mb-1 font-medium">Teure Lebensmittel</h2>
          <p class="mb-3 text-xs text-gray-500">
            Lebensmittelbudget: {{ eur(data.expensive.food_total) }}
          </p>
          <div
            v-for="e in data.expensive.by_total_spend"
            :key="e.name"
            class="flex items-center justify-between border-b py-1 text-sm last:border-0"
          >
            <button class="text-left hover:text-green-600" @click="selectItem(e.item_id, e.name)">
              {{ e.name }}
            </button>
            <span class="text-gray-600">
              {{ eur(e.total_spend) }}
              <template v-if="e.share_of_food_budget">
                · {{ (Number(e.share_of_food_budget) * 100).toFixed(0) }} %
              </template>
            </span>
          </div>
        </div>
      </div>

      <!-- Price trend -->
      <div class="rounded border bg-white p-4">
        <h2 class="mb-3 font-medium">
          Preisverlauf<span v-if="selectedItem"> — {{ selectedItem.name }}</span>
        </h2>
        <p v-if="!selectedItem" class="text-sm text-gray-500">
          Einen Artikel oben anklicken, um den Preisverlauf zu sehen.
        </p>
        <TrendChart v-else :points="trend" />
      </div>
    </template>
  </section>
</template>
