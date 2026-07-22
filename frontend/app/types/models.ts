// Frontend-facing types. These track the backend response shapes; once the
// receipt/analytics endpoints exist (step 2+), regenerate `types/api.d.ts`
// from the OpenAPI schema (`pnpm generate:api`) and align these with it.

export type ReceiptStatus =
  | 'uploaded'
  | 'processing'
  | 'done'
  | 'needs_review'
  | 'failed'

export type LineType = 'product' | 'deposit' | 'discount'

export interface Category {
  id: string
  name: string
  parentId: string | null
  sortOrder: number
}

export interface LineItem {
  id: string
  receiptId: string
  itemId: string | null
  categoryId: string | null
  name: string
  normalizedName: string | null
  quantity: number | null
  unit: string | null
  unitPrice: number | null
  totalPrice: number
  vatClass: string | null
  lineType: LineType
}

export interface Receipt {
  id: string
  storeName: string | null
  purchasedAt: string | null
  total: number | null
  currency: string
  status: ReceiptStatus
  confidence: string | null
  lineItems: LineItem[]
}
