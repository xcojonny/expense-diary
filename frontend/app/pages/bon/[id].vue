<script setup lang="ts">
import type { Category, LineItem, LineType, ReceiptDetail, ReceiptStatus } from '~/types/models'

const route = useRoute()
const router = useRouter()
const { api } = useApi()
const id = route.params.id as string

const { data, refresh } = await useAsyncData(`receipt-${id}`, () =>
  Promise.all([
    api<ReceiptDetail>(`/receipts/${id}`),
    api<Category[]>('/categories'),
  ]).then(([receipt, categories]) => ({ receipt, categories })),
)

const LINE_TYPES: { value: LineType, label: string }[] = [
  { value: 'product', label: 'Produkt' },
  { value: 'deposit', label: 'Pfand' },
  { value: 'discount', label: 'Rabatt' },
]

const STATUS: Record<ReceiptStatus, { label: string, cls: string }> = {
  uploaded: { label: 'Hochgeladen', cls: 'bg-gray-100 text-gray-600' },
  processing: { label: 'Wird verarbeitet …', cls: 'bg-blue-100 text-blue-700' },
  done: { label: 'Fertig', cls: 'bg-green-100 text-green-700' },
  needs_review: { label: 'Bitte prüfen', cls: 'bg-amber-100 text-amber-800' },
  failed: { label: 'Fehler', cls: 'bg-red-100 text-red-700' },
}

interface EditRow {
  id?: string
  name: string
  quantity: string
  unit: string
  unit_price: string
  total_price: string
  line_type: LineType
  category_id: string | null
  saving?: boolean
  savedAt?: number
}

function toRow(li: LineItem): EditRow {
  return {
    id: li.id,
    name: li.name,
    quantity: li.quantity ?? '',
    unit: li.unit ?? '',
    unit_price: li.unit_price ?? '',
    total_price: li.total_price,
    line_type: li.line_type,
    category_id: li.category_id,
  }
}

const rows = ref<EditRow[]>((data.value?.receipt.line_items ?? []).map(toRow))
const storeName = ref(data.value?.receipt.store_name ?? '')
const purchasedAt = ref(data.value?.receipt.purchased_at?.slice(0, 10) ?? '')

// Category dropdown grouped by parent (top-level + its children).
const catGroups = computed(() => {
  const cats = data.value?.categories ?? []
  const byOrder = (a: Category, b: Category) => a.sort_order - b.sort_order
  return cats
    .filter(c => !c.parent_id)
    .sort(byOrder)
    .map(top => ({
      ...top,
      children: cats.filter(c => c.parent_id === top.id).sort(byOrder),
    }))
})

const toNum = (v: string | null) => {
  const n = parseFloat(String(v ?? '').replace(',', '.'))
  return Number.isNaN(n) ? 0 : n
}
const money = (v: string | number | null) =>
  toNum(typeof v === 'number' ? String(v) : v).toLocaleString('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

// Live reconciliation: sum of line items vs the printed total.
const lineSum = computed(() => rows.value.reduce((s, r) => s + toNum(r.total_price), 0))
const printedTotal = computed(() => (data.value?.receipt.total != null ? toNum(data.value.receipt.total) : null))
const sumMatches = computed(
  () => printedTotal.value !== null && Math.abs(lineSum.value - printedTotal.value) < 0.02,
)
const uncategorized = computed(
  () => rows.value.filter(r => r.line_type === 'product' && !r.category_id).length,
)

// --- Feedback -------------------------------------------------------------
const notice = ref<{ type: 'success' | 'error', text: string } | null>(null)
let noticeTimer: ReturnType<typeof setTimeout> | null = null
function flash(type: 'success' | 'error', text: string) {
  notice.value = { type, text }
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = null), 3500)
}
onUnmounted(() => {
  if (noticeTimer) clearTimeout(noticeTimer)
})

function payload(row: EditRow) {
  const num = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    name: row.name.trim(),
    quantity: num(row.quantity),
    unit: row.unit.trim() || null,
    unit_price: num(row.unit_price),
    total_price: num(row.total_price) ?? '0',
    line_type: row.line_type,
    category_id: row.category_id || null,
  }
}

async function persist(row: EditRow) {
  if (row.id) {
    await api(`/receipts/${id}/line-items/${row.id}`, { method: 'PATCH', body: payload(row) })
  } else {
    const created = await api<LineItem>(`/receipts/${id}/line-items`, {
      method: 'POST',
      body: payload(row),
    })
    row.id = created.id
  }
  row.savedAt = Date.now()
}

async function saveRow(row: EditRow) {
  if (!row.name.trim()) return flash('error', 'Position braucht einen Namen.')
  row.saving = true
  try {
    await persist(row)
    await refresh()
    flash('success', `„${row.name.trim()}" gespeichert.`)
  } catch {
    flash('error', 'Speichern fehlgeschlagen.')
  } finally {
    row.saving = false
  }
}

async function saveAll() {
  const targets = rows.value.filter(r => r.name.trim())
  let failed = 0
  for (const row of targets) {
    row.saving = true
    try {
      await persist(row)
    } catch {
      failed++
    } finally {
      row.saving = false
    }
  }
  await refresh()
  flash(
    failed ? 'error' : 'success',
    failed
      ? `${failed} von ${targets.length} Positionen fehlgeschlagen.`
      : `Alle ${targets.length} Positionen gespeichert.`,
  )
}

async function deleteRow(row: EditRow, index: number) {
  try {
    if (row.id) await api(`/receipts/${id}/line-items/${row.id}`, { method: 'DELETE' })
    rows.value.splice(index, 1)
    flash('success', 'Position gelöscht.')
  } catch {
    flash('error', 'Löschen fehlgeschlagen.')
  }
}

function addRow() {
  rows.value.push({
    name: '',
    quantity: '',
    unit: '',
    unit_price: '',
    total_price: '',
    line_type: 'product',
    category_id: null,
  })
}

async function saveHeader() {
  try {
    await api(`/receipts/${id}`, {
      method: 'PATCH',
      body: { store_name: storeName.value || null, purchased_at: purchasedAt.value || null },
    })
    await refresh()
    flash('success', 'Kopfdaten gespeichert.')
  } catch {
    flash('error', 'Kopfdaten konnten nicht gespeichert werden.')
  }
}

async function confirmReview() {
  try {
    await api(`/receipts/${id}`, { method: 'PATCH', body: { status: 'done' } })
    await refresh()
    flash('success', 'Bon als geprüft markiert.')
  } catch {
    flash('error', 'Konnte nicht als geprüft markiert werden.')
  }
}

async function removeReceipt() {
  if (!confirm('Diesen Bon inklusive aller Positionen löschen?')) return
  await api(`/receipts/${id}`, { method: 'DELETE' })
  await router.push('/')
}
</script>

<template>
  <section v-if="data" class="space-y-4">
    <!-- Feedback banner -->
    <p
      v-if="notice"
      class="rounded px-3 py-2 text-sm"
      :class="notice.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'"
    >
      {{ notice.text }}
    </p>

    <div class="flex items-center justify-between">
      <NuxtLink to="/" class="text-sm text-gray-500 hover:underline">← Zurück</NuxtLink>
      <button class="text-sm text-red-600 hover:underline" @click="removeReceipt">Bon löschen</button>
    </div>

    <!-- Summary / status card -->
    <div class="rounded-lg border bg-white p-4 shadow-sm">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-lg font-semibold">{{ storeName || 'Unbekannter Markt' }}</h1>
            <span
              class="rounded-full px-2 py-0.5 text-xs font-medium"
              :class="STATUS[data.receipt.status].cls"
            >
              {{ STATUS[data.receipt.status].label }}
            </span>
          </div>
          <p class="mt-0.5 text-sm text-gray-500">
            {{ purchasedAt || 'ohne Datum' }} · {{ rows.length }} Positionen
          </p>
        </div>
        <div class="text-right">
          <p class="text-2xl font-semibold">{{ money(data.receipt.total) }} {{ data.receipt.currency }}</p>
          <p
            class="text-xs"
            :class="sumMatches ? 'text-green-600' : 'text-amber-600'"
          >
            <template v-if="printedTotal === null">Positionssumme {{ money(lineSum) }}</template>
            <template v-else-if="sumMatches">✓ Positionen ergeben die Summe</template>
            <template v-else>⚠ Positionen: {{ money(lineSum) }} (weicht ab)</template>
          </p>
        </div>
      </div>

      <!-- Failure detail -->
      <p v-if="data.receipt.status === 'failed' && data.receipt.error" class="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
        Fehler bei der Verarbeitung: {{ data.receipt.error }}
      </p>
      <!-- Review hint -->
      <p v-else-if="data.receipt.status === 'needs_review'" class="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
        Automatik unsicher — bitte Positionen prüfen und korrigieren, dann als geprüft markieren.
      </p>
      <p v-if="uncategorized" class="mt-2 text-xs text-gray-500">
        {{ uncategorized }} Position(en) ohne Kategorie — für die Auswertung bitte zuordnen.
      </p>

      <!-- Editable header + actions -->
      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label class="text-sm">
          <span class="text-gray-500">Markt</span>
          <input v-model="storeName" class="mt-1 w-full rounded border px-2 py-1.5">
        </label>
        <label class="text-sm">
          <span class="text-gray-500">Einkaufsdatum</span>
          <input v-model="purchasedAt" type="date" class="mt-1 w-full rounded border px-2 py-1.5">
        </label>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button class="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white" @click="saveHeader">
          Kopfdaten speichern
        </button>
        <button
          v-if="data.receipt.status === 'needs_review'"
          class="rounded border border-green-600 px-3 py-1.5 text-sm text-green-700"
          @click="confirmReview"
        >
          Als geprüft markieren
        </button>
      </div>
    </div>

    <!-- Items -->
    <div class="rounded-lg border bg-white shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b p-3">
        <h2 class="font-medium">Positionen</h2>
        <div class="flex gap-2">
          <button class="rounded border px-2 py-1 text-sm text-gray-600 hover:text-green-700" @click="addRow">
            + Position
          </button>
          <button class="rounded bg-green-600 px-3 py-1 text-sm font-medium text-white" @click="saveAll">
            Alle speichern
          </button>
        </div>
      </div>

      <ul class="divide-y">
        <li
          v-for="(row, i) in rows"
          :key="row.id ?? `new-${i}`"
          class="p-3"
          :class="row.line_type !== 'product' ? 'bg-gray-50' : ''"
        >
          <!-- Row 1: name + category -->
          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model="row.name"
              placeholder="Bezeichnung"
              class="min-w-40 flex-1 rounded border px-2 py-1.5 text-sm font-medium"
            >
            <select v-model="row.category_id" class="rounded border px-2 py-1.5 text-sm">
              <option :value="null">— Kategorie —</option>
              <optgroup v-for="g in catGroups" :key="g.id" :label="g.name">
                <option :value="g.id">{{ g.name }}</option>
                <option v-for="c in g.children" :key="c.id" :value="c.id">&nbsp;&nbsp;{{ c.name }}</option>
              </optgroup>
            </select>
          </div>
          <!-- Row 2: numbers + type + actions -->
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <label class="flex items-center gap-1 text-gray-500">
              Menge
              <input v-model="row.quantity" class="w-16 rounded border px-1.5 py-1 text-right text-gray-900">
            </label>
            <label class="flex items-center gap-1 text-gray-500">
              Einheit
              <input v-model="row.unit" class="w-14 rounded border px-1.5 py-1 text-gray-900">
            </label>
            <label class="flex items-center gap-1 text-gray-500">
              Stück
              <input v-model="row.unit_price" class="w-20 rounded border px-1.5 py-1 text-right text-gray-900">
            </label>
            <label class="flex items-center gap-1 text-gray-500">
              Gesamt
              <input v-model="row.total_price" class="w-20 rounded border px-1.5 py-1 text-right font-medium text-gray-900">
            </label>
            <select v-model="row.line_type" class="rounded border px-1.5 py-1 text-gray-700">
              <option v-for="t in LINE_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <div class="ml-auto flex items-center gap-3">
              <span v-if="row.savedAt" class="text-xs text-green-600">gespeichert ✓</span>
              <button
                class="text-green-700 hover:underline disabled:opacity-50"
                :disabled="row.saving"
                @click="saveRow(row)"
              >
                {{ row.saving ? '…' : 'Speichern' }}
              </button>
              <button class="text-red-600 hover:underline" @click="deleteRow(row, i)">Löschen</button>
            </div>
          </div>
        </li>
      </ul>

      <p v-if="!rows.length" class="p-4 text-sm text-gray-500">
        Keine Positionen. Über „+ Position" eine anlegen.
      </p>
    </div>
  </section>
</template>
