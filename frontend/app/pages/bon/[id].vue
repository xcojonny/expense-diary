<script setup lang="ts">
import type { Category, LineItem, LineType, ReceiptDetail } from '~/types/models'

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

const LINE_TYPES: LineType[] = ['product', 'deposit', 'discount']

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

function payload(row: EditRow) {
  const num = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    name: row.name,
    quantity: num(row.quantity),
    unit: row.unit.trim() || null,
    unit_price: num(row.unit_price),
    total_price: num(row.total_price) ?? '0',
    line_type: row.line_type,
    category_id: row.category_id || null,
  }
}

async function saveRow(row: EditRow) {
  row.saving = true
  try {
    if (row.id) {
      await api(`/receipts/${id}/line-items/${row.id}`, { method: 'PATCH', body: payload(row) })
    } else {
      const created = await api<LineItem>(`/receipts/${id}/line-items`, {
        method: 'POST',
        body: payload(row),
      })
      row.id = created.id
    }
    await refresh()
  } finally {
    row.saving = false
  }
}

async function deleteRow(row: EditRow, index: number) {
  if (row.id) await api(`/receipts/${id}/line-items/${row.id}`, { method: 'DELETE' })
  rows.value.splice(index, 1)
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
  await api(`/receipts/${id}`, {
    method: 'PATCH',
    body: { store_name: storeName.value || null, purchased_at: purchasedAt.value || null },
  })
  await refresh()
}

async function confirmReview() {
  await api(`/receipts/${id}`, { method: 'PATCH', body: { status: 'done' } })
  await refresh()
}

async function removeReceipt() {
  await api(`/receipts/${id}`, { method: 'DELETE' })
  await router.push('/')
}
</script>

<template>
  <section v-if="data" class="space-y-5">
    <div class="flex items-center justify-between">
      <NuxtLink to="/" class="text-sm text-gray-500 hover:underline">← Zurück</NuxtLink>
      <button class="text-sm text-red-600 hover:underline" @click="removeReceipt">Bon löschen</button>
    </div>

    <div class="rounded border bg-white p-4">
      <div class="grid grid-cols-2 gap-3">
        <label class="text-sm">
          <span class="text-gray-500">Markt</span>
          <input v-model="storeName" class="mt-1 w-full rounded border px-2 py-1">
        </label>
        <label class="text-sm">
          <span class="text-gray-500">Einkaufsdatum</span>
          <input v-model="purchasedAt" type="date" class="mt-1 w-full rounded border px-2 py-1">
        </label>
      </div>
      <div class="mt-3 flex items-center gap-3">
        <button class="rounded bg-green-600 px-3 py-1.5 text-sm text-white" @click="saveHeader">
          Kopf speichern
        </button>
        <span class="text-sm text-gray-500">
          Summe: {{ data.receipt.total ?? '—' }} {{ data.receipt.currency }} ·
          Status: {{ data.receipt.status }}
        </span>
        <button
          v-if="data.receipt.status === 'needs_review'"
          class="rounded border border-green-600 px-3 py-1.5 text-sm text-green-700"
          @click="confirmReview"
        >
          Als geprüft markieren
        </button>
      </div>
    </div>

    <div class="rounded border bg-white">
      <table class="w-full text-sm">
        <thead class="border-b text-left text-gray-500">
          <tr>
            <th class="p-2">Position</th>
            <th class="p-2">Menge</th>
            <th class="p-2">Einheit</th>
            <th class="p-2 text-right">Stückpreis</th>
            <th class="p-2 text-right">Gesamt</th>
            <th class="p-2">Typ</th>
            <th class="p-2">Kategorie</th>
            <th class="p-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="row.id ?? `new-${i}`" class="border-b">
            <td class="p-2"><input v-model="row.name" class="w-full rounded border px-1"></td>
            <td class="p-2"><input v-model="row.quantity" class="w-16 rounded border px-1"></td>
            <td class="p-2"><input v-model="row.unit" class="w-14 rounded border px-1"></td>
            <td class="p-2 text-right"><input v-model="row.unit_price" class="w-20 rounded border px-1 text-right"></td>
            <td class="p-2 text-right"><input v-model="row.total_price" class="w-20 rounded border px-1 text-right"></td>
            <td class="p-2">
              <select v-model="row.line_type" class="rounded border px-1">
                <option v-for="t in LINE_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </td>
            <td class="p-2">
              <select v-model="row.category_id" class="max-w-[10rem] rounded border px-1">
                <option :value="null">—</option>
                <option v-for="c in data.categories" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </td>
            <td class="whitespace-nowrap p-2 text-right">
              <button class="text-green-600 hover:underline" :disabled="row.saving" @click="saveRow(row)">
                Speichern
              </button>
              <button class="ml-2 text-red-600 hover:underline" @click="deleteRow(row, i)">Löschen</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="p-2">
        <button class="text-sm text-green-600 hover:underline" @click="addRow">+ Position hinzufügen</button>
      </div>
    </div>
  </section>
</template>
