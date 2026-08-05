"""Pydantic-Schemas — der API-Vertrag.

Alle Beträge sind `int` in Cent, Mengen `int` in Tausendstel, Anteile `int` in
Basispunkten (ADR-003). Das Suffix im Feldnamen macht die Einheit an jeder
Verwendungsstelle sichtbar — auch im generierten TypeScript-Typ.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str


class HouseholdOut(ApiModel):
    id: int
    name: str


class MembershipOut(BaseModel):
    household_id: int
    household_name: str
    role: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    memberships: list[MembershipOut]


class SessionInfo(ApiModel):
    authenticated: bool
    auth_mode: str
    # Bei trusted_header/none gibt es keine Anmeldemaske — die UI blendet sie aus.
    login_required: bool
    # Nur in mehrbenutzerfähigen Modi gibt es Haushalte und Einladungen.
    multi_user: bool = False
    # SSO-Knopf nur zeigen, wenn OIDC wirklich konfiguriert ist.
    sso_available: bool = False
    user: UserOut | None = None
    active_household_id: int | None = None


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class HouseholdUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberOut(BaseModel):
    id: int
    user_id: int
    email: str
    display_name: str
    role: str


class MemberUpdate(BaseModel):
    role: str = Field(pattern="^(admin|member)$")


class InvitationOut(ApiModel):
    id: int
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member", pattern="^(admin|member)$")


class InvitationCreated(BaseModel):
    invitation: InvitationOut
    # Der Link wird per Mail verschickt. Ohne SMTP steht er hier, damit man ihn
    # weitergeben kann — `mail_sent` sagt, welcher Fall vorliegt.
    link: str
    mail_sent: bool


class InvitationAccept(BaseModel):
    token: str = Field(min_length=8)


# --- Kategorien ---------------------------------------------------------------


class CategoryOut(ApiModel):
    id: int
    name: str
    parent_id: int | None
    sort_order: int
    is_food: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    sort_order: int = 100
    is_food: bool | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: int | None = None
    # Explizit, weil `parent_id: null` in JSON nicht von „nicht gesetzt" zu
    # unterscheiden ist.
    clear_parent: bool = False
    sort_order: int | None = None
    is_food: bool | None = None


# --- Positionen ---------------------------------------------------------------


class LineItemOut(ApiModel):
    id: int
    position: int
    name: str
    quantity_milli: int | None
    unit: str | None
    unit_price_cents: int | None
    total_price_cents: int
    vat_class: str | None
    kind: str
    category_id: int | None
    item_id: int | None


class LineItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    total_price_cents: int
    quantity_milli: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=16)
    unit_price_cents: int | None = None
    category_id: int | None = None
    kind: str = Field(default="product", pattern="^(product|deposit|discount)$")
    vat_class: str | None = Field(default=None, max_length=4)


class LineItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    total_price_cents: int | None = None
    quantity_milli: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=16)
    unit_price_cents: int | None = None
    category_id: int | None = None
    clear_category: bool = False
    kind: str | None = Field(default=None, pattern="^(product|deposit|discount)$")


# --- Bons ---------------------------------------------------------------------


class ReceiptOut(ApiModel):
    id: int
    status: str
    store_name: str | None
    purchased_at: datetime | None
    total_cents: int | None
    currency: str
    confidence: str | None
    error: str | None
    source: str
    file_media_type: str | None
    created_at: datetime
    line_items: list[LineItemOut] = Field(default_factory=list)


class ReceiptSummary(ApiModel):
    """Listenansicht — ohne Positionen, aber mit deren Anzahl."""

    id: int
    status: str
    store_name: str | None
    purchased_at: datetime | None
    total_cents: int | None
    currency: str
    line_item_count: int
    created_at: datetime


class ReceiptPage(BaseModel):
    items: list[ReceiptSummary]
    total: int


class ReceiptUpdate(BaseModel):
    store_name: str | None = Field(default=None, max_length=160)
    purchased_at: datetime | None = None
    total_cents: int | None = None


# --- Auswertung ---------------------------------------------------------------


class CategorySpendOut(BaseModel):
    category_id: int | None
    category_name: str
    total_cents: int
    share_bp: int | None


class StoreSpendOut(BaseModel):
    store_name: str
    total_cents: int
    receipt_count: int


class TopLineItemOut(BaseModel):
    name: str
    total_price_cents: int
    day: date
    store_name: str | None


class MonthlyReportOut(BaseModel):
    year: int
    month: int
    receipt_count: int
    unreviewed_count: int
    total_cents: int
    product_total_cents: int
    deposit_total_cents: int
    discount_total_cents: int
    food_total_cents: int
    by_category: list[CategorySpendOut]
    by_store: list[StoreSpendOut]
    top_items: list[TopLineItemOut]


class ItemStatOut(BaseModel):
    item_id: int | None
    name: str
    purchases: int
    total_quantity_milli: int
    unit: str | None
    total_spend_cents: int
    avg_unit_price_cents: int | None
    is_food: bool
    share_of_food_bp: int | None


class ItemRankingOut(BaseModel):
    food_total_cents: int
    sort: str
    items: list[ItemStatOut]


class TrendPointOut(BaseModel):
    day: date
    unit_price_cents: int
    purchases: int


class PriceTrendOut(BaseModel):
    item_id: int
    name: str
    points: list[TrendPointOut]


class CategoryDeltaOut(BaseModel):
    category_name: str
    current_cents: int
    previous_cents: int
    delta_cents: int


class ComparisonOut(BaseModel):
    current_cents: int
    previous_cents: int
    delta_cents: int
    delta_bp: int | None
    by_category: list[CategoryDeltaOut]


# --- Tokens -------------------------------------------------------------------


class ApiTokenOut(ApiModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ApiTokenCreated(ApiModel):
    token: ApiTokenOut
    # Genau einmal sichtbar — danach existiert nur der Hash.
    plaintext: str


# --- Health -------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str
    version: str
    auth_mode: str
    multi_user: bool
    llm_provider: str
    llm_ready: bool
    mail_ready: bool
    queued_jobs: int
