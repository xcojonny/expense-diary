<script setup lang="ts">
/**
 * Bon erfassen — mit Live-Status.
 *
 * Nach dem Upload wird der Bon gepollt, bis die Extraktion einen Endzustand
 * erreicht (der Worker läuft im API-Prozess, ADR-002). Das Polling stoppt, wenn
 * nichts mehr offen ist, und wird beim Verlassen der Seite abgeräumt — der
 * Altstand ließ das Intervall weiterlaufen.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, ApiError } from '@/lib/api'
import { formatCents } from '@/lib/money'
import { toast } from '@/lib/toast'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UploadZone, { type PendingFile } from '@/components/UploadZone.vue'
import { useSession } from '@/stores/session'
import type { Receipt } from '@/types/api'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiIcon from '@/ui/UiIcon.vue'

const router = useRouter()
const { refreshHealth } = useSession()

const queue = ref<PendingFile[]>([])
const results = ref<Receipt[]>([])
let nextId = 1
let poller: number | null = null

const POLL_MS = 2000

const pendingCount = computed(
  () => results.value.filter((r) => r.status === 'uploaded' || r.status === 'processing').length,
)

function stopPolling(): void {
  if (poller !== null) {
    window.clearInterval(poller)
    poller = null
  }
}

async function pollOnce(): Promise<void> {
  const open = results.value.filter((r) => r.status === 'uploaded' || r.status === 'processing')
  if (!open.length) {
    stopPolling()
    void refreshHealth()
    return
  }
  await Promise.all(
    open.map(async (receipt) => {
      try {
        const fresh = await api.get<Receipt>(`/receipts/${receipt.id}`)
        results.value = results.value.map((entry) => (entry.id === fresh.id ? fresh : entry))
      } catch {
        /* nächster Durchlauf versucht es wieder */
      }
    }),
  )
}

function startPolling(): void {
  if (poller !== null) return
  poller = window.setInterval(() => void pollOnce(), POLL_MS)
}

async function uploadOne(entry: PendingFile): Promise<void> {
  entry.state = 'uploading'
  const form = new FormData()
  form.append('file', entry.file)
  try {
    const receipt = await api.post<Receipt>('/receipts', form)
    entry.state = 'done'
    entry.receiptId = receipt.id
    results.value = [receipt, ...results.value]
    startPolling()
  } catch (caught) {
    entry.state = 'error'
    entry.message = caught instanceof ApiError ? caught.message : 'Upload fehlgeschlagen.'
    toast.error(`${entry.file.name}: ${entry.message}`)
  }
}

async function onFiles(files: File[]): Promise<void> {
  const added: PendingFile[] = files.map((file) => ({
    id: nextId++,
    file,
    // Vorschau nur für Bilder; PDFs bekommen ein Symbol.
    previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
    state: 'queued',
  }))
  queue.value = [...queue.value, ...added]

  // Nacheinander hochladen: bei fünf Fotos vom Handy ist das freundlicher zum
  // Upstream als fünf parallele Requests.
  for (const entry of added) {
    await uploadOne(entry)
  }
}

function clearQueue(): void {
  for (const entry of queue.value) {
    if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl)
  }
  queue.value = []
  results.value = []
  stopPolling()
}

onBeforeUnmount(() => {
  stopPolling()
  for (const entry of queue.value) {
    if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl)
  }
})
</script>

<template>
  <div>
    <PageHeader title="Bon erfassen" subtitle="Foto, PDF oder Screenshot — die Positionen liest die App selbst aus.">
      <template #actions>
        <UiButton v-if="queue.length" variant="ghost" size="sm" @click="clearQueue">
          Liste leeren
        </UiButton>
      </template>
    </PageHeader>

    <div class="stack">
      <UploadZone :items="queue" @files="onFiles" />

      <UiCard
        v-if="results.length"
        title="Ergebnis"
        :hint="pendingCount ? `${pendingCount} Bon(s) werden noch gelesen …` : 'Alles gelesen.'"
        flush
      >
        <ul class="results">
          <li v-for="receipt in results" :key="receipt.id" class="result">
            <div class="result__head">
              <div class="result__title">
                <span class="result__store">{{ receipt.store_name ?? 'Unbekannter Markt' }}</span>
                <span class="subtle">
                  {{ receipt.line_items.length }} Positionen
                  <template v-if="receipt.total_cents !== null">
                    · {{ formatCents(receipt.total_cents) }}
                  </template>
                </span>
              </div>
              <div class="row">
                <StatusBadge :status="receipt.status" />
                <UiButton
                  variant="secondary"
                  size="sm"
                  @click="router.push(`/bons/${receipt.id}`)"
                >
                  Öffnen
                  <UiIcon name="chevronRight" :size="14" />
                </UiButton>
              </div>
            </div>

            <p v-if="receipt.error" class="result__error">{{ receipt.error }}</p>

            <ul v-if="receipt.line_items.length" class="preview-lines">
              <li v-for="line in receipt.line_items.slice(0, 4)" :key="line.id">
                <span class="truncate">{{ line.name }}</span>
                <span class="num">{{ formatCents(line.total_price_cents) }}</span>
              </li>
              <li v-if="receipt.line_items.length > 4" class="subtle">
                … und {{ receipt.line_items.length - 4 }} weitere
              </li>
            </ul>
          </li>
        </ul>
      </UiCard>
    </div>
  </div>
</template>

<style scoped>
.results {
  padding: 0;
  margin: 0;
  list-style: none;
}

.result {
  padding: 13px 16px;
}

.result + .result {
  border-top: 1px solid var(--border);
}

.result__head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.result__title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.result__store {
  font-weight: 550;
}

.result__error {
  margin-top: 9px;
  padding: 9px 11px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  background: var(--warn-soft);
  border-radius: var(--radius-sm);
  overflow-wrap: anywhere;
}

.preview-lines {
  padding: 0;
  margin: 10px 0 0;
  list-style: none;
}

.preview-lines li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 0;
  font-size: 0.8125rem;
  color: var(--text-muted);
}
</style>
