<script setup lang="ts">
/**
 * Übersicht — die Startseite.
 *
 * Jedes Widget hat seine eigene Ressource. Fällt `/analytics/compare` aus,
 * bleiben Kennzahlen und Bon-Liste stehen; im Altstand war dann die ganze Seite
 * leer, weil ein `Promise.all` alles zusammenhielt.
 */
import { computed } from 'vue'

import { useResource } from '@/lib/useResource'
import { api } from '@/lib/api'
import { formatBpSigned, formatCents, formatCentsRounded } from '@/lib/money'
import { monthLabel } from '@/lib/format'
import PageHeader from '@/components/PageHeader.vue'
import ReceiptList from '@/components/ReceiptList.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import ChartBars from '@/charts/ChartBars.vue'
import type { Comparison, MonthlyReport, ReceiptPage } from '@/types/api'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiEmpty from '@/ui/UiEmpty.vue'
import UiStat from '@/ui/UiStat.vue'

const now = new Date()

const monthly = useResource(() => api.get<MonthlyReport>('/analytics/monthly'))
const comparison = useResource(() => api.get<Comparison>('/analytics/compare'))
const recent = useResource(() => api.get<ReceiptPage>('/receipts', { limit: 8 }))

const label = monthLabel(now.getFullYear(), now.getMonth() + 1)

const trend = computed(() => {
  const data = comparison.data.value
  if (!data || data.delta_bp === null) return null
  return {
    text: `${formatBpSigned(data.delta_bp)} gegenüber Vormonat`,
    direction: data.delta_cents > 0 ? ('up' as const) : ('down' as const),
  }
})

const categoryRows = computed(() =>
  (monthly.data.value?.by_category ?? []).slice(0, 5).map((entry, index) => ({
    key: entry.category_id ?? entry.category_name,
    label: entry.category_name,
    value: formatCents(entry.total_cents),
    weight: entry.total_cents,
    colorIndex: index,
  })),
)

const hasReceipts = computed(() => (recent.data.value?.total ?? 0) > 0)
</script>

<template>
  <div>
    <PageHeader title="Übersicht" :subtitle="label">
      <template #actions>
        <UiButton variant="primary" icon="camera" @click="$router.push('/upload')">
          Bon erfassen
        </UiButton>
      </template>
    </PageHeader>

    <div class="stack">
      <!-- Kennzahlen -->
      <ResourceBoundary
        :loading="monthly.loading.value"
        :error="monthly.error.value"
        skeleton-height="92px"
        :skeleton-lines="1"
        @retry="monthly.reload"
      >
        <div v-if="monthly.data.value" class="grid-cards">
          <UiStat
            accent
            label="Ausgaben"
            :value="formatCentsRounded(monthly.data.value.total_cents)"
            :delta="trend?.text"
            :direction="trend?.direction ?? null"
            :hint="trend ? undefined : 'kein Vormonatsvergleich'"
          />
          <UiStat
            label="Lebensmittel"
            :value="formatCentsRounded(monthly.data.value.food_total_cents)"
            :hint="`von ${formatCentsRounded(monthly.data.value.product_total_cents)} Warenwert`"
          />
          <UiStat
            label="Bons"
            :value="String(monthly.data.value.receipt_count)"
            :hint="
              monthly.data.value.unreviewed_count
                ? `${monthly.data.value.unreviewed_count} zu prüfen`
                : 'alle geprüft'
            "
          />
          <UiStat
            label="Rabatte"
            :value="formatCentsRounded(Math.abs(monthly.data.value.discount_total_cents))"
            :hint="`Pfand ${formatCents(monthly.data.value.deposit_total_cents)}`"
          />
        </div>
      </ResourceBoundary>

      <div class="columns">
        <!-- Top-Kategorien -->
        <UiCard title="Wohin das Geld geht" hint="Top-Kategorien diesen Monat">
          <template #actions>
            <UiButton variant="ghost" size="sm" @click="$router.push('/bericht')">
              Bericht
            </UiButton>
          </template>
          <ResourceBoundary
            :loading="monthly.loading.value"
            :error="monthly.error.value"
            :empty="categoryRows.length === 0"
            empty-title="Noch keine kategorisierten Ausgaben"
            empty-icon="tag"
            @retry="monthly.reload"
          >
            <ChartBars :rows="categoryRows" colorful />
          </ResourceBoundary>
        </UiCard>

        <!-- Letzte Bons -->
        <UiCard title="Letzte Bons" flush>
          <template #actions>
            <UiButton variant="ghost" size="sm" @click="$router.push('/bons')">Alle</UiButton>
          </template>
          <div class="card-pad">
            <ResourceBoundary
              :loading="recent.loading.value"
              :error="recent.error.value"
              :empty="!hasReceipts"
              @retry="recent.reload"
            >
              <template #empty>
                <UiEmpty
                  title="Noch kein Bon erfasst"
                  hint="Fotografiere den ersten Kassenbon — die Positionen liest die App selbst aus."
                >
                  <UiButton variant="primary" icon="camera" @click="$router.push('/upload')">
                    Ersten Bon erfassen
                  </UiButton>
                </UiEmpty>
              </template>
              <ReceiptList :receipts="recent.data.value?.items ?? []" />
            </ResourceBoundary>
          </div>
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

/* Die Bon-Liste läuft randlos, der Lade-/Leerzustand braucht aber Abstand. */
.card-pad :deep(.skeleton-group),
.card-pad :deep(.failure) {
  margin: 14px 16px;
}
</style>
