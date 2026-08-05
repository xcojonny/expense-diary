<script setup lang="ts">
/**
 * Bericht — das Herzstück.
 *
 * Vier unabhängige Ressourcen, die auf den Monat hören. Der Preisverlauf lädt
 * erst, wenn ein Artikel angeklickt wird (`lazy`), und deckt zwölf Monate ab,
 * weil ein Trend mehr als einen Monat braucht.
 */
import { computed, ref } from 'vue'

import { api } from '@/lib/api'
import { useResource } from '@/lib/useResource'
import {
  formatBp,
  formatBpSigned,
  formatCents,
  formatCentsRounded,
  formatQuantityWithUnit,
} from '@/lib/money'
import { formatDateShort, monthLabel, pluralize } from '@/lib/format'
import ChartBars, { type BarRow } from '@/charts/ChartBars.vue'
import ChartDonut from '@/charts/ChartDonut.vue'
import ChartLine, { type LinePoint } from '@/charts/ChartLine.vue'
import MonthPicker from '@/components/MonthPicker.vue'
import PageHeader from '@/components/PageHeader.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import type { Comparison, ItemRanking, ItemSort, MonthlyReport, PriceTrend } from '@/types/api'
import UiBadge from '@/ui/UiBadge.vue'
import UiCard from '@/ui/UiCard.vue'
import UiSegmented from '@/ui/UiSegmented.vue'
import UiStat from '@/ui/UiStat.vue'

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)

const sort = ref<ItemSort>('spend')
const selectedItem = ref<{ id: number; name: string } | null>(null)

const monthly = useResource(
  () => api.get<MonthlyReport>('/analytics/monthly', { year: year.value, month: month.value }),
  { watch: [year, month] },
)
const comparison = useResource(
  () => api.get<Comparison>('/analytics/compare', { year: year.value, month: month.value }),
  { watch: [year, month] },
)
const ranking = useResource(
  () =>
    api.get<ItemRanking>('/analytics/items', {
      year: year.value,
      month: month.value,
      sort: sort.value,
      limit: 12,
    }),
  { watch: [year, month, sort] },
)
const trend = useResource(
  () =>
    selectedItem.value
      ? api.get<PriceTrend>(`/analytics/price-trend/${selectedItem.value.id}`, { months: 12 })
      : Promise.resolve(null),
  { lazy: true, watch: [selectedItem] },
)

const SORT_SEGMENTS = [
  { value: 'spend', label: 'Teuerste' },
  { value: 'frequency', label: 'Häufigste' },
  { value: 'unit_price', label: 'Stückpreis' },
]

const SORT_HINTS: Record<ItemSort, string> = {
  spend: 'Wo im Monat das meiste Geld hingegangen ist.',
  frequency: 'Was am häufigsten im Wagen lag — der Blick auf „zu viel gekauft“.',
  unit_price: 'Was pro Stück oder Kilo am teuersten war.',
}

const empty = computed(() => (monthly.data.value?.receipt_count ?? 0) === 0)

const trendDirection = computed(() => {
  const data = comparison.data.value
  if (!data || data.delta_bp === null) return null
  return data.delta_cents > 0 ? ('up' as const) : ('down' as const)
})

const donutSlices = computed(() =>
  (monthly.data.value?.by_category ?? []).map((entry) => ({
    key: entry.category_id ?? entry.category_name,
    label: entry.category_name,
    value: formatCents(entry.total_cents),
    weight: entry.total_cents,
  })),
)

const storeRows = computed<BarRow[]>(() =>
  (monthly.data.value?.by_store ?? []).map((entry, index) => ({
    key: entry.store_name,
    label: entry.store_name,
    value: formatCents(entry.total_cents),
    meta: pluralize(entry.receipt_count, 'Bon', 'Bons'),
    weight: entry.total_cents,
    colorIndex: index,
  })),
)

const itemRows = computed<BarRow[]>(() =>
  (ranking.data.value?.items ?? []).map((item) => {
    const parts: string[] = [`${item.purchases}×`]
    if (item.total_quantity_milli) {
      parts.push(formatQuantityWithUnit(item.total_quantity_milli, item.unit))
    }
    if (item.avg_unit_price_cents !== null) {
      parts.push(`Ø ${formatCents(item.avg_unit_price_cents)}`)
    }
    if (item.share_of_food_bp !== null) {
      parts.push(`${formatBp(item.share_of_food_bp)} des Essensbudgets`)
    }
    return {
      key: item.item_id ?? item.name,
      label: item.name,
      value:
        sort.value === 'unit_price'
          ? formatCents(item.avg_unit_price_cents)
          : formatCents(item.total_spend_cents),
      meta: parts.join(' · '),
      weight: sort.value === 'frequency' ? item.purchases : item.total_spend_cents,
      clickable: item.item_id !== null,
      active: selectedItem.value?.id === item.item_id,
    }
  }),
)

const topRows = computed<BarRow[]>(() =>
  (monthly.data.value?.top_items ?? []).map((item) => ({
    key: `${item.name}-${item.day}`,
    label: item.name,
    value: formatCents(item.total_price_cents),
    meta: [formatDateShort(item.day), item.store_name].filter(Boolean).join(' · '),
    weight: item.total_price_cents,
  })),
)

const categoryDeltas = computed(() =>
  (comparison.data.value?.by_category ?? []).filter((entry) => entry.delta_cents !== 0).slice(0, 8),
)

const trendPoints = computed<LinePoint[]>(() =>
  (trend.data.value?.points ?? []).map((point) => ({
    label: formatDateShort(point.day),
    value: point.unit_price_cents,
    display: formatCents(point.unit_price_cents),
    meta: point.purchases > 1 ? `${point.purchases} Käufe, Mittel` : undefined,
  })),
)

function selectItem(row: BarRow): void {
  const item = ranking.data.value?.items.find((entry) => (entry.item_id ?? entry.name) === row.key)
  if (!item?.item_id) return
  selectedItem.value =
    selectedItem.value?.id === item.item_id ? null : { id: item.item_id, name: item.name }
}
</script>

<template>
  <div>
    <PageHeader title="Bericht" :subtitle="monthLabel(year, month)">
      <template #actions>
        <MonthPicker v-model:year="year" v-model:month="month" />
      </template>
    </PageHeader>

    <div class="stack">
      <!-- Kennzahlen -->
      <ResourceBoundary
        :loading="monthly.loading.value"
        :error="monthly.error.value"
        :skeleton-lines="1"
        skeleton-height="92px"
        @retry="monthly.reload"
      >
        <div v-if="monthly.data.value" class="grid-cards">
          <UiStat
            accent
            label="Gesamt"
            :value="formatCentsRounded(monthly.data.value.total_cents)"
            :delta="
              comparison.data.value?.delta_bp !== null && comparison.data.value
                ? `${formatBpSigned(comparison.data.value.delta_bp)} ggü. Vormonat`
                : null
            "
            :direction="trendDirection"
            hint="kein Vormonatsvergleich"
          />
          <UiStat
            label="Lebensmittel"
            :value="formatCentsRounded(monthly.data.value.food_total_cents)"
            :hint="`von ${formatCentsRounded(monthly.data.value.product_total_cents)} Warenwert`"
          />
          <UiStat
            label="Pfand"
            :value="formatCents(monthly.data.value.deposit_total_cents)"
            hint="inkl. Leergut-Rückgaben"
          />
          <UiStat
            label="Rabatte"
            :value="formatCents(Math.abs(monthly.data.value.discount_total_cents))"
            hint="gespart durch Aktionen"
          />
        </div>
      </ResourceBoundary>

      <p v-if="monthly.data.value?.unreviewed_count" class="hint">
        {{ pluralize(monthly.data.value.unreviewed_count, 'Bon', 'Bons') }} in diesem Monat
        {{ monthly.data.value.unreviewed_count === 1 ? 'ist' : 'sind' }} noch nicht geprüft — die
        Zahlen zählen mit, könnten sich also noch ändern.
        <RouterLink to="/bons">Jetzt prüfen</RouterLink>
      </p>

      <div class="columns">
        <!-- Kategorien -->
        <UiCard title="Ausgaben nach Kategorie">
          <ResourceBoundary
            :loading="monthly.loading.value"
            :error="monthly.error.value"
            :empty="empty || donutSlices.length === 0"
            empty-title="Keine Ausgaben in diesem Monat"
            empty-icon="chart"
            @retry="monthly.reload"
          >
            <ChartDonut
              :slices="donutSlices"
              center-label="Warenwert"
              :center-value="formatCentsRounded(monthly.data.value?.product_total_cents ?? 0)"
            />
          </ResourceBoundary>
        </UiCard>

        <!-- Märkte -->
        <UiCard title="Ausgaben pro Markt">
          <ResourceBoundary
            :loading="monthly.loading.value"
            :error="monthly.error.value"
            :empty="storeRows.length === 0"
            empty-title="Keine Märkte erfasst"
            empty-icon="store"
            @retry="monthly.reload"
          >
            <ChartBars :rows="storeRows" colorful />
          </ResourceBoundary>
        </UiCard>
      </div>

      <!-- Artikel-Ranking -->
      <UiCard title="Artikel" :hint="SORT_HINTS[sort]">
        <template #actions>
          <UiSegmented v-model="sort" :segments="SORT_SEGMENTS" aria-label="Sortierung" />
        </template>
        <ResourceBoundary
          :loading="ranking.loading.value"
          :error="ranking.error.value"
          :empty="itemRows.length === 0"
          empty-title="Keine Artikel in diesem Monat"
          empty-hint="Sobald Bons mit Positionen erfasst sind, erscheint hier die Rangliste."
          empty-icon="receipt"
          @retry="ranking.reload"
        >
          <p class="subtle click-hint">Artikel antippen für den Preisverlauf.</p>
          <ChartBars :rows="itemRows" @select="selectItem" />
        </ResourceBoundary>
      </UiCard>

      <!-- Preisverlauf -->
      <UiCard
        title="Preisverlauf"
        :hint="selectedItem ? `${selectedItem.name} · letzte 12 Monate` : 'Artikel oben auswählen'"
      >
        <template v-if="selectedItem" #actions>
          <UiBadge tone="accent">{{ selectedItem.name }}</UiBadge>
        </template>

        <ResourceBoundary
          v-if="selectedItem"
          :loading="trend.loading.value"
          :error="trend.error.value"
          :empty="trendPoints.length === 0"
          :skeleton-lines="1"
          skeleton-height="200px"
          empty-title="Kein Stückpreis hinterlegt"
          empty-hint="Für einen Verlauf braucht dieser Artikel Positionen mit Menge und Stückpreis."
          empty-icon="chart"
          @retry="trend.reload"
        >
          <ChartLine :points="trendPoints" :format-tick="(value) => formatCents(Math.round(value))" />
        </ResourceBoundary>

        <p v-else class="subtle placeholder">
          Ein Klick auf einen Artikel in der Liste zeigt, wie sich sein Stückpreis über die
          Monate entwickelt hat.
        </p>
      </UiCard>

      <div class="columns">
        <!-- Teuerste Einzelpositionen -->
        <UiCard title="Teuerste Einzelpositionen" hint="Größte Einzelposten im Monat">
          <ResourceBoundary
            :loading="monthly.loading.value"
            :error="monthly.error.value"
            :empty="topRows.length === 0"
            empty-title="Keine Positionen"
            @retry="monthly.reload"
          >
            <ChartBars :rows="topRows" />
          </ResourceBoundary>
        </UiCard>

        <!-- Vormonatsvergleich -->
        <UiCard title="Gegenüber Vormonat" hint="Größte Veränderungen je Kategorie">
          <ResourceBoundary
            :loading="comparison.loading.value"
            :error="comparison.error.value"
            :empty="categoryDeltas.length === 0"
            empty-title="Kein Vergleich möglich"
            empty-hint="Es fehlen Daten aus dem Vormonat."
            empty-icon="chart"
            @retry="comparison.reload"
          >
            <ul class="deltas">
              <li v-for="entry in categoryDeltas" :key="entry.category_name" class="delta">
                <span class="truncate">{{ entry.category_name }}</span>
                <span class="delta__values">
                  <span class="subtle num">
                    {{ formatCents(entry.previous_cents) }} →
                    {{ formatCents(entry.current_cents) }}
                  </span>
                  <span
                    class="delta__change num"
                    :class="entry.delta_cents > 0 ? 'delta__change--up' : 'delta__change--down'"
                  >
                    {{ entry.delta_cents > 0 ? '+' : '' }}{{ formatCents(entry.delta_cents) }}
                  </span>
                </span>
              </li>
            </ul>
          </ResourceBoundary>
        </UiCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.columns {
  display: grid;
  gap: 14px;
  align-items: start;
  grid-template-columns: 1fr;
}

@media (width >= 1000px) {
  .columns {
    grid-template-columns: 1fr 1fr;
  }
}

.hint {
  padding: 11px 13px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  background: var(--warn-soft);
  border-radius: var(--radius);
}

.click-hint {
  margin-bottom: 8px;
}

.placeholder {
  padding: 14px 0;
}

.deltas {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.delta {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
  padding: 7px 0;
  font-size: 0.875rem;
}

.delta + .delta {
  border-top: 1px solid var(--border);
}

.delta__values {
  display: flex;
  flex: none;
  gap: 10px;
  align-items: baseline;
}

.delta__change {
  font-weight: 560;
}

.delta__change--up {
  color: var(--trend-up);
}

.delta__change--down {
  color: var(--trend-down);
}

@media (width <= 520px) {
  .delta__values {
    flex-direction: column;
    align-items: flex-end;
    gap: 1px;
  }
}
</style>
