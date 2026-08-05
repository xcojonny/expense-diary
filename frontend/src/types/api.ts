/**
 * API-Typen — Spiegel von `backend/app/schemas`.
 *
 * Das Suffix `_cents` / `_milli` / `_bp` bleibt im Typ stehen. Damit sieht man
 * an jeder Verwendungsstelle, dass hier keine Euro-Zahl steht (ADR-003).
 */

export type ReceiptStatus = 'uploaded' | 'processing' | 'done' | 'needs_review' | 'failed'
export type LineKind = 'product' | 'deposit' | 'discount'
export type ItemSort = 'frequency' | 'spend' | 'unit_price'
export type AuthMode = 'password' | 'oidc' | 'trusted_header' | 'none'
export type Role = 'admin' | 'member'

export interface Membership {
  household_id: number
  household_name: string
  role: Role
}

export interface CurrentUser {
  id: number
  email: string
  display_name: string
  memberships: Membership[]
}

export interface SessionInfo {
  authenticated: boolean
  auth_mode: AuthMode
  login_required: boolean
  /** Nur in `oidc`/`trusted_header` gibt es mehrere Menschen und Einladungen. */
  multi_user: boolean
  /** SSO-Knopf nur zeigen, wenn OIDC vollständig konfiguriert ist. */
  sso_available: boolean
  user: CurrentUser | null
  active_household_id: number | null
}

export interface Household {
  id: number
  name: string
}

export interface Member {
  id: number
  user_id: number
  email: string
  display_name: string
  role: Role
}

export interface Invitation {
  id: number
  email: string
  role: Role
  expires_at: string
  created_at: string
}

export interface InvitationCreated {
  invitation: Invitation
  link: string
  mail_sent: boolean
}

export interface Health {
  status: string
  version: string
  auth_mode: AuthMode
  multi_user: boolean
  llm_provider: string
  llm_ready: boolean
  mail_ready: boolean
  queued_jobs: number
}

export interface Category {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  is_food: boolean
}

export interface LineItem {
  id: number
  position: number
  name: string
  quantity_milli: number | null
  unit: string | null
  unit_price_cents: number | null
  total_price_cents: number
  vat_class: string | null
  kind: LineKind
  category_id: number | null
  item_id: number | null
}

export interface Receipt {
  id: number
  status: ReceiptStatus
  store_name: string | null
  purchased_at: string | null
  total_cents: number | null
  currency: string
  confidence: string | null
  error: string | null
  source: string
  file_media_type: string | null
  created_at: string
  line_items: LineItem[]
}

export interface ReceiptSummary {
  id: number
  status: ReceiptStatus
  store_name: string | null
  purchased_at: string | null
  total_cents: number | null
  currency: string
  line_item_count: number
  created_at: string
}

export interface ReceiptPage {
  items: ReceiptSummary[]
  total: number
}

export interface CategorySpend {
  category_id: number | null
  category_name: string
  total_cents: number
  share_bp: number | null
}

export interface StoreSpend {
  store_name: string
  total_cents: number
  receipt_count: number
}

export interface TopLineItem {
  name: string
  total_price_cents: number
  day: string
  store_name: string | null
}

export interface MonthlyReport {
  year: number
  month: number
  receipt_count: number
  unreviewed_count: number
  total_cents: number
  product_total_cents: number
  deposit_total_cents: number
  discount_total_cents: number
  food_total_cents: number
  by_category: CategorySpend[]
  by_store: StoreSpend[]
  top_items: TopLineItem[]
}

export interface ItemStat {
  item_id: number | null
  name: string
  purchases: number
  total_quantity_milli: number
  unit: string | null
  total_spend_cents: number
  avg_unit_price_cents: number | null
  is_food: boolean
  share_of_food_bp: number | null
}

export interface ItemRanking {
  food_total_cents: number
  sort: ItemSort
  items: ItemStat[]
}

export interface TrendPoint {
  day: string
  unit_price_cents: number
  purchases: number
}

export interface PriceTrend {
  item_id: number
  name: string
  points: TrendPoint[]
}

export interface CategoryDelta {
  category_name: string
  current_cents: number
  previous_cents: number
  delta_cents: number
}

export interface Comparison {
  current_cents: number
  previous_cents: number
  delta_cents: number
  delta_bp: number | null
  by_category: CategoryDelta[]
}

export interface ApiToken {
  id: number
  name: string
  created_at: string
  last_used_at: string | null
}

export interface ApiTokenCreated {
  token: ApiToken
  plaintext: string
}
