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

// --- Analysis layer (decimals arrive as strings) -----------------------------

export interface CategorySpend {
  category_id: string | null
  category_name: string
  total: string
}

export interface StoreSpend {
  store_name: string
  total: string
}

export interface TopLineItem {
  name: string
  total_price: string
  day: string
  store_name: string | null
}

export interface MonthlyReport {
  year: number
  month: number
  receipt_count: number
  total_spending: string
  product_total: string
  deposit_total: string
  discount_total: string
  by_category: CategorySpend[]
  by_store: StoreSpend[]
  top_items: TopLineItem[]
}

export interface ItemUsage {
  item_id: string | null
  name: string
  count: number
  total_quantity: string
  unit: string | null
  total_spend: string
}

export interface ExpensiveItem {
  item_id: string | null
  name: string
  total_spend: string
  avg_unit_price: string | null
  occurrences: number
  share_of_food_budget: string | null
}

export interface ExpensiveItemsReport {
  food_total: string
  by_total_spend: ExpensiveItem[]
  by_unit_price: ExpensiveItem[]
}

export interface TrendPoint {
  day: string
  unit_price: string
  occurrences: number
}

export interface CategoryDelta {
  category_name: string
  current: string
  previous: string
  delta: string
}

export interface Comparison {
  current_total: string
  previous_total: string
  delta: string
  delta_pct: string | null
  by_category: CategoryDelta[]
}
