<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/lib/api'
import { useResource } from '@/lib/useResource'
import { pluralize } from '@/lib/format'
import PageHeader from '@/components/PageHeader.vue'
import ReceiptList from '@/components/ReceiptList.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import type { ReceiptPage, ReceiptStatus } from '@/types/api'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiEmpty from '@/ui/UiEmpty.vue'
import UiSegmented from '@/ui/UiSegmented.vue'

const PAGE_SIZE = 25

const filter = ref<'all' | ReceiptStatus>('all')
const page = ref(0)

const receipts = useResource(
  () =>
    api.get<ReceiptPage>('/receipts', {
      status: filter.value === 'all' ? undefined : filter.value,
      limit: PAGE_SIZE,
      offset: page.value * PAGE_SIZE,
    }),
  { watch: [filter, page] },
)

const segments = [
  { value: 'all', label: 'Alle' },
  { value: 'needs_review', label: 'Zu prüfen' },
  { value: 'done', label: 'Fertig' },
  { value: 'failed', label: 'Fehler' },
]

const total = computed(() => receipts.data.value?.total ?? 0)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

// Beim Filterwechsel zurück auf Seite 1 — sonst zeigt Seite 3 eines Filters
// mit zwei Treffern nichts an.
function setFilter(value: string): void {
  filter.value = value as 'all' | ReceiptStatus
  page.value = 0
}
</script>

<template>
  <div>
    <PageHeader title="Bons" :subtitle="pluralize(total, 'Bon', 'Bons') + ' erfasst'">
      <template #actions>
        <UiButton variant="primary" icon="camera" @click="$router.push('/upload')">
          Bon erfassen
        </UiButton>
      </template>
    </PageHeader>

    <div class="stack">
      <div class="scroll-x">
        <UiSegmented
          :model-value="filter"
          :segments="segments"
          aria-label="Bons filtern"
          @update:model-value="setFilter"
        />
      </div>

      <UiCard flush>
        <div class="pad">
          <ResourceBoundary
            :loading="receipts.loading.value"
            :error="receipts.error.value"
            :empty="total === 0"
            @retry="receipts.reload"
          >
            <template #empty>
              <UiEmpty
                :title="filter === 'all' ? 'Noch kein Bon erfasst' : 'Keine Bons in dieser Ansicht'"
                :hint="
                  filter === 'all'
                    ? 'Fotografiere den ersten Kassenbon — die Positionen liest die App selbst aus.'
                    : 'Wechsle den Filter, um andere Bons zu sehen.'
                "
              >
                <UiButton
                  v-if="filter === 'all'"
                  variant="primary"
                  icon="camera"
                  @click="$router.push('/upload')"
                >
                  Ersten Bon erfassen
                </UiButton>
              </UiEmpty>
            </template>
            <ReceiptList :receipts="receipts.data.value?.items ?? []" />
          </ResourceBoundary>
        </div>
      </UiCard>

      <div v-if="pageCount > 1" class="pager">
        <UiButton
          variant="secondary"
          size="sm"
          icon="chevronLeft"
          :disabled="page === 0"
          @click="page -= 1"
        >
          Zurück
        </UiButton>
        <span class="subtle num">Seite {{ page + 1 }} von {{ pageCount }}</span>
        <UiButton
          variant="secondary"
          size="sm"
          :disabled="page + 1 >= pageCount"
          @click="page += 1"
        >
          Weiter
        </UiButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pad :deep(.skeleton-group),
.pad :deep(.failure) {
  margin: 14px 16px;
}

.pager {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
}
</style>
