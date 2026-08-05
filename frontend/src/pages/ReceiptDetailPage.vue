<script setup lang="ts">
/**
 * Bon-Detail: Kopf und Positionen korrigieren, Originalbeleg daneben.
 *
 * Die Summenprüfung („Positionen ergeben X, gedruckt steht Y") wird hier
 * sichtbar gemacht — sie ist der Grund, warum ein Bon in `needs_review` landet,
 * und ohne Anzeige rät man beim Korrigieren.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, ApiError } from '@/lib/api'
import { formatCents } from '@/lib/money'
import { formatDateTime, fromDateInput, toDateInput } from '@/lib/format'
import { toast } from '@/lib/toast'
import LineItemRow, { type LineItemPatch } from '@/components/LineItemRow.vue'
import PageHeader from '@/components/PageHeader.vue'
import ReceiptPreview from '@/components/ReceiptPreview.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useCategories } from '@/stores/categories'
import { useResource } from '@/lib/useResource'
import type { LineItem, Receipt } from '@/types/api'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'
import UiModal from '@/ui/UiModal.vue'
import UiMoneyInput from '@/ui/UiMoneyInput.vue'

const route = useRoute()
const router = useRouter()
const { ensureLoaded } = useCategories()

const receiptId = Number(route.params.id)

const resource = useResource(() => api.get<Receipt>(`/receipts/${receiptId}`))
const receipt = computed(() => resource.data.value)

const savingHeader = ref(false)
const savingLine = ref<number | null>(null)
const confirmDelete = ref(false)
const busy = ref(false)

const storeName = ref('')
const purchasedAt = ref('')
const totalCents = ref<number | null>(null)
let headerLoadedFor: number | null = null

let poller: number | null = null

function syncHeader(data: Receipt): void {
  storeName.value = data.store_name ?? ''
  purchasedAt.value = toDateInput(data.purchased_at)
  totalCents.value = data.total_cents
  headerLoadedFor = data.id
}

async function refresh(): Promise<void> {
  await resource.reload()
  const data = resource.data.value
  if (data && headerLoadedFor !== data.id) syncHeader(data)
}

/** Solange die Extraktion läuft, den Status nachziehen. */
function managePolling(): void {
  const status = receipt.value?.status
  const running = status === 'uploaded' || status === 'processing'
  if (running && poller === null) {
    poller = window.setInterval(() => void refresh(), 2000)
  } else if (!running && poller !== null) {
    window.clearInterval(poller)
    poller = null
  }
}

const lineSum = computed(() =>
  (receipt.value?.line_items ?? []).reduce((sum, line) => sum + line.total_price_cents, 0),
)

/** Toleranz wie im Backend: 2 Cent oder 1 %. */
const sumMismatch = computed(() => {
  const printed = receipt.value?.total_cents
  if (printed === null || printed === undefined || !receipt.value?.line_items.length) return null
  const tolerance = Math.max(2, Math.floor(Math.abs(printed) / 100))
  const difference = lineSum.value - printed
  return Math.abs(difference) > tolerance ? difference : null
})

async function saveHeader(): Promise<void> {
  savingHeader.value = true
  try {
    resource.data.value = await api.patch<Receipt>(`/receipts/${receiptId}`, {
      store_name: storeName.value,
      purchased_at: fromDateInput(purchasedAt.value),
      total_cents: totalCents.value,
    })
    toast.success('Kopfdaten gespeichert.')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Speichern fehlgeschlagen.')
  } finally {
    savingHeader.value = false
  }
}

async function saveLine(line: LineItem, patch: LineItemPatch): Promise<void> {
  savingLine.value = line.id
  try {
    await api.patch<LineItem>(`/line-items/${line.id}`, patch)
    await refresh()
    toast.success('Position gespeichert.')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Speichern fehlgeschlagen.')
  } finally {
    savingLine.value = null
  }
}

async function removeLine(line: LineItem): Promise<void> {
  try {
    await api.delete(`/line-items/${line.id}`)
    await refresh()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Löschen fehlgeschlagen.')
  }
}

async function addLine(): Promise<void> {
  try {
    await api.post<LineItem>(`/receipts/${receiptId}/line-items`, {
      name: 'Neue Position',
      total_price_cents: 0,
    })
    await refresh()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Anlegen fehlgeschlagen.')
  }
}

async function markReviewed(): Promise<void> {
  busy.value = true
  try {
    resource.data.value = await api.post<Receipt>(`/receipts/${receiptId}/reviewed`)
    toast.success('Als geprüft markiert.')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Fehlgeschlagen.')
  } finally {
    busy.value = false
  }
}

async function reprocess(): Promise<void> {
  busy.value = true
  try {
    resource.data.value = await api.post<Receipt>(`/receipts/${receiptId}/reprocess`)
    toast.info('Bon wird neu gelesen …')
    managePolling()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Fehlgeschlagen.')
  } finally {
    busy.value = false
  }
}

async function deleteReceipt(): Promise<void> {
  try {
    await api.delete(`/receipts/${receiptId}`)
    toast.success('Bon gelöscht.')
    await router.push('/bons')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Löschen fehlgeschlagen.')
  } finally {
    confirmDelete.value = false
  }
}

onMounted(async () => {
  await ensureLoaded()
  await refresh()
  managePolling()
})

onBeforeUnmount(() => {
  if (poller !== null) window.clearInterval(poller)
})
</script>

<template>
  <div>
    <PageHeader
      :title="receipt?.store_name || 'Bon'"
      :subtitle="receipt ? formatDateTime(receipt.purchased_at ?? receipt.created_at) : undefined"
    >
      <template #actions>
        <UiButton variant="ghost" size="sm" icon="chevronLeft" @click="$router.push('/bons')">
          Bons
        </UiButton>
        <UiButton variant="secondary" size="sm" icon="refresh" :loading="busy" @click="reprocess">
          Neu lesen
        </UiButton>
        <UiButton variant="danger" size="sm" icon="trash" @click="confirmDelete = true">
          Löschen
        </UiButton>
      </template>
    </PageHeader>

    <ResourceBoundary
      :loading="resource.loading.value"
      :error="resource.error.value"
      :skeleton-lines="4"
      skeleton-height="60px"
      @retry="resource.reload"
    >
      <div v-if="receipt" class="detail">
        <div class="detail__main stack">
          <!-- Status und Hinweise -->
          <div class="statusbar">
            <StatusBadge :status="receipt.status" />
            <span v-if="receipt.confidence" class="subtle">
              Zuversicht: {{ receipt.confidence }}
            </span>
            <span class="detail__spacer" />
            <UiButton
              v-if="receipt.status === 'needs_review'"
              variant="primary"
              size="sm"
              icon="check"
              :loading="busy"
              @click="markReviewed"
            >
              Als geprüft markieren
            </UiButton>
          </div>

          <p v-if="receipt.error" class="notice notice--warn">
            <UiIcon name="warning" :size="16" />
            <span>{{ receipt.error }}</span>
          </p>

          <p v-if="sumMismatch !== null" class="notice notice--warn">
            <UiIcon name="warning" :size="16" />
            <span>
              Positionen ergeben <strong class="num">{{ formatCents(lineSum) }}</strong>, auf dem Bon
              steht <strong class="num">{{ formatCents(receipt.total_cents) }}</strong>
              (Differenz <span class="num">{{ formatCents(sumMismatch) }}</span>). Bitte prüfen.
            </span>
          </p>

          <!-- Kopfdaten -->
          <UiCard title="Kopfdaten">
            <form class="header-form" @submit.prevent="saveHeader">
              <UiField v-slot="{ id }" label="Markt">
                <UiInput :id="id" v-model="storeName" placeholder="z. B. REWE" />
              </UiField>
              <UiField v-slot="{ id }" label="Einkaufsdatum">
                <UiInput :id="id" v-model="purchasedAt" type="date" />
              </UiField>
              <UiField v-slot="{ id }" label="Endsumme (wie gedruckt)">
                <UiMoneyInput :id="id" v-model="totalCents" />
              </UiField>
              <div class="header-form__submit">
                <UiButton variant="primary" type="submit" :loading="savingHeader">
                  Speichern
                </UiButton>
              </div>
            </form>
          </UiCard>

          <!-- Positionen -->
          <UiCard
            title="Positionen"
            :hint="`Summe der Positionen: ${formatCents(lineSum)}`"
            flush
          >
            <template #actions>
              <UiButton variant="secondary" size="sm" icon="plus" @click="addLine">
                Position
              </UiButton>
            </template>

            <ul v-if="receipt.line_items.length" class="lines">
              <LineItemRow
                v-for="line in receipt.line_items"
                :key="line.id"
                :item="line"
                :saving="savingLine === line.id"
                @save="(patch) => saveLine(line, patch)"
                @remove="removeLine(line)"
              />
            </ul>
            <p v-else class="lines__empty">
              Keine Positionen erkannt. Über „Position“ von Hand erfassen oder „Neu lesen“ versuchen.
            </p>
          </UiCard>
        </div>

        <!-- Originalbeleg -->
        <aside class="detail__aside">
          <UiCard title="Originalbeleg" hint="Zum Vergleichen beim Korrigieren">
            <ReceiptPreview :receipt-id="receipt.id" :media-type="receipt.file_media_type" />
          </UiCard>
        </aside>
      </div>
    </ResourceBoundary>

    <UiModal
      v-if="confirmDelete"
      title="Bon löschen?"
      confirm-label="Endgültig löschen"
      danger
      @close="confirmDelete = false"
      @confirm="deleteReceipt"
    >
      Der Bon, seine Positionen und die Beleg-Datei werden entfernt. Die Auswertungen der
      betroffenen Monate ändern sich dadurch.
    </UiModal>
  </div>
</template>

<style scoped>
.detail {
  display: grid;
  gap: 14px;
  align-items: start;
  grid-template-columns: 1fr;
}

@media (width >= 1080px) {
  .detail {
    grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  }

  .detail__aside {
    position: sticky;
    top: 24px;
  }
}

.statusbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.detail__spacer {
  flex: 1;
}

.notice {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 11px 13px;
  font-size: 0.8125rem;
  border-radius: var(--radius);
  overflow-wrap: anywhere;
}

.notice--warn {
  background: var(--warn-soft);
}

.notice--warn svg {
  flex: none;
  color: var(--warn);
}

.header-form {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  align-items: end;
}

.header-form__submit {
  display: flex;
  justify-content: flex-end;
}

.lines {
  padding: 0;
  margin: 0;
  list-style: none;
}

.lines__empty {
  padding: 18px 16px;
  font-size: 0.875rem;
  color: var(--text-muted);
}
</style>
