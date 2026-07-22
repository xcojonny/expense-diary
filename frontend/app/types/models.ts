// Frontend-facing types, aligned with the backend response shapes (snake_case,
// as FastAPI/Pydantic emit them). Once the OpenAPI schema stabilizes,
// regenerate `types/api.d.ts` via `pnpm generate:api` and derive from it.

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
  parent_id: string | null
  sort_order: number
}

export interface LineItem {
  id: string
  name: string
  normalized_name: string | null
  quantity: string | null
  unit: string | null
  unit_price: string | null
  total_price: string
  vat_class: string | null
  line_type: LineType
  category_id: string | null
  item_id: string | null
}

export interface Receipt {
  id: string
  store_name: string | null
  purchased_at: string | null
  total: string | null
  currency: string
  status: ReceiptStatus
  confidence: string | null
  created_at: string
}

export interface ReceiptDetail extends Receipt {
  error: string | null
  line_items: LineItem[]
}

// Statuses at which extraction has finished and polling should stop.
export const TERMINAL_STATUSES: ReceiptStatus[] = ['done', 'needs_review', 'failed']
