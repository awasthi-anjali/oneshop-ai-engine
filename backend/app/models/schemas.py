from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductCategory(str, Enum):
    PHONE = "phone"
    TABLET = "tablet"
    PLAN = "plan"
    ACCESSORY = "accessory"
    DEVICE = "device"


class Product(BaseModel):
    id: str
    name: str
    category: ProductCategory
    brand: str
    price: float
    description: str
    features: list[str] = Field(default_factory=list)
    specs: dict[str, Any] = Field(default_factory=dict)
    image_url: str = ""
    rating: float = 4.0
    in_stock: bool = True
    tags: list[str] = Field(default_factory=list)
    currency: str = "USD"
    billing_period: str = "one_time"

    @model_validator(mode="after")
    def set_billing_period(self) -> "Product":
        if self.category == ProductCategory.PLAN:
            self.billing_period = "monthly"
        return self


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str
    products: list[Product] = Field(default_factory=list)
    comparison: list[Product] | None = None


class ChatChannel(str, Enum):
    ONESHOP = "oneshop"
    ONEAPP = "oneapp"


class PageSurface(str, Enum):
    CATALOG = "catalog"
    PRODUCT = "product"
    CART = "cart"


class EntryPoint(str, Enum):
    HELP_ME_CHOOSE = "help_me_choose"
    PRODUCT_DETAIL = "product_detail"
    NEXT_BEST_ACTION = "next_best_action"
    CART = "cart"


class PageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface: PageSurface
    entry_point: EntryPoint
    product_id: str | None = None
    visible_product_ids: list[str] = Field(default_factory=list, max_length=20)


class PersonalizationContext(BaseModel):
    """Validated UI hint for contract compatibility; server-derived preferences remain authoritative."""

    model_config = ConfigDict(extra="forbid")

    preferred_brands: list[str] = Field(default_factory=list, max_length=3)
    preferred_categories: list[ProductCategory] = Field(default_factory=list, max_length=3)
    price_centroid: float = Field(default=0, ge=0, le=100_000)
    interaction_count: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("preferred_brands")
    @classmethod
    def normalize_preferred_brands(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.strip().split())[:32] for value in values]
        return [value for value in normalized if value]


class CheckoutConfirmationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(..., min_length=16, max_length=128)
    confirmation_token: str = Field(..., min_length=16, max_length=256)
    idempotency_key: str = Field(
        ...,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None
    channel: ChatChannel = ChatChannel.ONESHOP
    user_id: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    personalization_context: PersonalizationContext | None = None
    page_context: PageContext | None = None
    checkout_confirmation: CheckoutConfirmationContext | None = None

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class NeedProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(default_factory=list, max_length=2)
    use_cases: list[str] = Field(default_factory=list, max_length=8)
    device_budget_max: float | None = Field(default=None, ge=0)
    monthly_budget_max: float | None = Field(default=None, ge=0)
    platform: str | None = None
    roaming_required: bool | None = None
    lines: int | None = Field(default=None, ge=1)
    must_haves: list[str] = Field(default_factory=list, max_length=8)
    nice_to_haves: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, values: list[str]) -> list[str]:
        if any(value not in {"phone", "plan"} for value in values):
            raise ValueError("unsupported ShopAssist category")
        return values

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str | None) -> str | None:
        if value is not None and value not in {"android", "ios"}:
            raise ValueError("platform must be android or ios")
        return value


class RecommendationSlot(str, Enum):
    PRIMARY_PHONE = "primary_phone"
    ALTERNATIVE_PHONE = "alternative_phone"
    RECOMMENDED_PLAN = "recommended_plan"


class ReasonCode(str, Enum):
    WITHIN_DEVICE_BUDGET = "WITHIN_DEVICE_BUDGET"
    WITHIN_MONTHLY_BUDGET = "WITHIN_MONTHLY_BUDGET"
    CAMERA_MATCH = "CAMERA_MATCH"
    ROAMING_MATCH = "ROAMING_MATCH"
    DATA_MATCH = "DATA_MATCH"
    PLATFORM_MATCH = "PLATFORM_MATCH"
    COMPACT_MATCH = "COMPACT_MATCH"
    FAST_CHARGING_MATCH = "FAST_CHARGING_MATCH"
    FAMILY_LINES_MATCH = "FAMILY_LINES_MATCH"
    PRODUCT_CONTEXT_MATCH = "PRODUCT_CONTEXT_MATCH"


class ShopAssistRecommendation(BaseModel):
    product: Product
    slot: RecommendationSlot
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    reason: str


class ShopAssistActionType(str, Enum):
    REFINE = "REFINE"
    COMPARE = "COMPARE"
    OPEN_PRODUCT = "OPEN_PRODUCT"
    VIEW_CART = "VIEW_CART"
    PROPOSE_ADD_TO_CART = "PROPOSE_ADD_TO_CART"
    PROPOSE_ADD_BUNDLE = "PROPOSE_ADD_BUNDLE"
    PROPOSE_REMOVE_FROM_CART = "PROPOSE_REMOVE_FROM_CART"
    OPEN_CHECKOUT = "OPEN_CHECKOUT"
    HANDOFF_SERVICE = "HANDOFF_SERVICE"


class ShopAssistAction(BaseModel):
    type: ShopAssistActionType
    label: str
    product_ids: list[str] = Field(default_factory=list)
    proposal_id: str | None = None


class CartSummary(BaseModel):
    items: list[Product] = Field(default_factory=list)
    total_items: int = 0
    one_time_total: float = 0
    monthly_total: float = 0


class CartProposal(BaseModel):
    proposal_id: str
    operation: str = Field(default="add", pattern=r"^(add|remove)$")
    cart_version: int = Field(ge=0)
    products: list[Product] = Field(..., min_length=1, max_length=20)
    product_ids: list[str] = Field(..., min_length=1, max_length=20)
    excluded_product_ids: list[str] = Field(default_factory=list)
    one_time_total: float = 0
    monthly_total: float = 0
    resulting_one_time_total: float = 0
    resulting_monthly_total: float = 0
    expires_at: str | None = None


class ChatStatus(str, Enum):
    CLARIFYING = "clarifying"
    RECOMMENDED = "recommended"
    NO_MATCH = "no_match"
    UNSUPPORTED = "unsupported"
    SERVICE_HANDOFF = "service_handoff"
    ERROR = "error"


class ChatMode(str, Enum):
    AI = "ai"
    FALLBACK = "fallback"


class ChatResponse(BaseModel):
    session_id: str
    status: ChatStatus
    message: str
    need_profile: NeedProfile = Field(default_factory=NeedProfile)
    recommendations: list[ShopAssistRecommendation] = Field(default_factory=list, max_length=3)
    comparison: list[Product] | None = None
    actions: list[ShopAssistAction] = Field(default_factory=list)
    mode: ChatMode = ChatMode.FALLBACK
    suggested_actions: list[str] = Field(default_factory=list)
    cart_updated: bool = False
    open_checkout: bool = False
    selected_tool: str | None = None
    cart_summary: CartSummary | None = None
    cart_proposal: CartProposal | None = None
    checkout_review_status: str | None = None
    order_receipt: "OrderReceipt | None" = None


class CartConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., min_length=16, max_length=128)
    idempotency_key: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    session_id: str = Field(..., min_length=1, max_length=128)
    user_id: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    channel: ChatChannel = ChatChannel.ONESHOP


class CartConfirmationResponse(BaseModel):
    session_id: str
    proposal_id: str
    cart_version: int = Field(ge=0)
    operation: str = Field(default="add", pattern=r"^(add|remove)$")
    added_product_ids: list[str] = Field(default_factory=list)
    removed_product_ids: list[str] = Field(default_factory=list)
    excluded_product_ids: list[str] = Field(default_factory=list)
    idempotent_replay: bool = False
    cart_summary: CartSummary


class DemoPaymentMethod(str, Enum):
    SUCCESS = "demo_card_success"
    DECLINED = "demo_card_declined"


class CheckoutReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=128)
    user_id: str | None = Field(
        default=None,
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    customer_name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=3, max_length=254)
    demo_payment_method: DemoPaymentMethod

    @field_validator("customer_name")
    @classmethod
    def normalize_customer_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if any(char in normalized for char in "\r\n"):
            raise ValueError("customer_name contains invalid characters")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            any(char in normalized for char in "\r\n,;")
            or normalized.count("@") != 1
            or "." not in normalized.rsplit("@", 1)[1]
        ):
            raise ValueError("Enter a valid email address")
        return normalized


class CheckoutReviewItem(BaseModel):
    product_id: str
    name: str
    category: str
    currency: str
    billing_period: str
    unit_amount_minor: int


class CheckoutReviewResponse(BaseModel):
    review_id: str
    session_id: str
    cart_version: int = Field(ge=0)
    status: str
    items: list[CheckoutReviewItem]
    one_time_total_minor: int
    monthly_total_minor: int
    customer_name: str
    email: str
    payment_mode: str = "demo_simulated"
    payment_status: str = "simulated"
    payment_last4: str
    confirmation_token: str | None = None
    expires_at: str
    consumed_order_id: str | None = None


class OrderItemSnapshot(BaseModel):
    product_id: str
    name: str
    category: str
    currency: str
    billing_period: str
    unit_amount_minor: int


class OrderReceipt(BaseModel):
    order_id: str
    session_id: str
    status: str = "demo_order_confirmed"
    payment_mode: str = "demo_simulated"
    payment_status: str = "simulated"
    payment_last4: str
    customer_name: str
    email: str
    items: list[OrderItemSnapshot]
    one_time_total_minor: int
    monthly_total_minor: int
    created_at: str
    idempotent_replay: bool = False
    email_status: str = "pending"
    email_attempts: int = 0
    email_provider: str | None = None


class ProductSearchRequest(BaseModel):
    query: str = ""
    category: ProductCategory | None = None
    max_price: float | None = None
    min_price: float | None = None
    brand: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = 10


class ProductSearchResponse(BaseModel):
    products: list[Product] = Field(default_factory=list)
    search_method: str = "name"  # name | embeddings | keyword


class CompareRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=2, max_length=4)


class CustomerIntent(BaseModel):
    categories: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    price_avg: float | None = None
    summary: str = ""
    funnel_stage: str = "new"
    ecosystem: str = ""
    purchase_readiness: str = ""


class RecommendationItem(BaseModel):
    product: Product
    score: float
    reason: str
    source: str = "rules"  # ai | semantic_backup | rules


class RecommendationsResponse(BaseModel):
    session_id: str
    intent: CustomerIntent
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    ai_powered: bool = False


class NextBestAction(BaseModel):
    action: str
    label: str
    priority: int = 1


class NextBestActionResponse(BaseModel):
    session_id: str
    funnel_stage: str
    actions: list[NextBestAction] = Field(default_factory=list)
    ai_powered: bool = False


class BundleSuggestion(BaseModel):
    name: str
    products: list[Product]
    product_ids: list[str] = Field(default_factory=list)
    total_price: float
    original_price: float = 0
    discount_percent: float = 0
    savings: float
    reason: str


class CrossSellItem(BaseModel):
    product: Product
    rate: int
    reason: str


class SmartCartResponse(BaseModel):
    session_id: str
    cart: list[Product] = Field(default_factory=list)
    bundles: list[BundleSuggestion] = Field(default_factory=list)
    cross_sell_suggestions: list[CrossSellItem] = Field(default_factory=list)
    nudge: str = ""
    checkout_tip: str = ""
    ai_powered: bool = False
    subtotal: float = 0
    discount: float = 0
    total: float = 0
    estimated_savings: float = 0
    one_time_total: float = 0
    monthly_total: float = 0


class BundleAddRequest(BaseModel):
    session_id: str | None = None
    product_ids: list[str] = Field(..., min_length=1)
    channel: str | None = None


class AbandonmentResponse(BaseModel):
    session_id: str
    is_abandoned: bool
    recovery_message: str = ""
    discount_offer: float = 0
    cart_count: int = 0


class IntelligenceProfileResponse(BaseModel):
    session_id: str
    intent: CustomerIntent
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    next_actions: list[NextBestAction] = Field(default_factory=list)
    funnel_stage: str = "new"
    cart: list[Product] = Field(default_factory=list)
    bundles: list[BundleSuggestion] = Field(default_factory=list)
    cross_sell_suggestions: list[CrossSellItem] = Field(default_factory=list)
    nudge: str = ""
    checkout_tip: str = ""
    subtotal: float = 0
    discount: float = 0
    total: float = 0
    estimated_savings: float = 0
    one_time_total: float = 0
    monthly_total: float = 0
    ai_powered: bool = False
    abandonment: AbandonmentResponse | None = None
    # Pipeline visibility (Phase 1 features 2 & 3)
    recommendation_pipeline: str = "rules"  # ai_validated | semantic_backup | rules
    retrieval_method: str = "none"  # embeddings | keyword | none
    retrieved_product_ids: list[str] = Field(default_factory=list)
    retrieval_query: str = ""
    # Omnichannel
    current_channel: str = ""
    last_channel: str = ""
    channels_used: list[str] = Field(default_factory=list)
    is_cross_channel: bool = False
    other_channel: str | None = None
    sync_message: str = ""
    customer_id: str | None = None
    continue_url_web: str = ""
    continue_url_app: str = ""


class OmnichannelLinkRequest(BaseModel):
    customer_id: str = Field(..., min_length=2)
    session_id: str | None = None


class OmnichannelLinkResponse(BaseModel):
    session_id: str
    customer_id: str
    message: str


class OmnichannelContextResponse(BaseModel):
    session_id: str
    customer_id: str | None = None
    current_channel: str
    last_channel: str
    channels_used: list[str] = Field(default_factory=list)
    is_cross_channel: bool = False
    other_channel: str | None = None
    other_channel_label: str = ""
    sync_message: str = ""
    cart_count: int = 0
    wishlist_count: int = 0
    viewed_count: int = 0
    continue_url_web: str = ""
    continue_url_app: str = ""
    funnel_stage: str = "new"


class SessionStateResponse(BaseModel):
    session_id: str
    cart_version: int = Field(ge=0)
    wishlist: list[Product] = Field(default_factory=list)
    cart: list[Product] = Field(default_factory=list)
    viewed: list[Product] = Field(default_factory=list)
    wishlist_ids: list[str] = Field(default_factory=list)
    cart_ids: list[str] = Field(default_factory=list)
    viewed_ids: list[str] = Field(default_factory=list)


class SessionActionRequest(BaseModel):
    session_id: str | None = None
    product_id: str
    channel: str | None = None


class RecommendationEventType(str, Enum):
    IMPRESSION = "impression"
    REC_CLICK = "rec_click"
    PRODUCT_VIEW = "product_view"
    WISHLIST_ADD = "wishlist_add"
    WISHLIST_REMOVE = "wishlist_remove"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    DISMISS = "dismiss"


class RecommendationEventMetadata(BaseModel):
    """Strict metadata allow-list: never persist raw chat, arbitrary payloads, or PII."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=120)
    intent: str | None = Field(default=None, max_length=64)
    rec_position: int | None = Field(default=None, ge=0, le=50)
    rec_type: str | None = Field(default=None, max_length=32)
    surface: str | None = Field(default=None, max_length=32)
    visible: bool | None = None

    @field_validator("query", "intent", "rec_type", "surface")
    @classmethod
    def normalize_metadata_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().lower().split())
        return normalized or None


class RecommendationInteractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    user_id: str = Field(..., min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    event_type: RecommendationEventType
    product_id: str | None = None
    channel: ChatChannel = ChatChannel.ONESHOP
    session_id: str | None = Field(default=None, max_length=128)
    metadata: RecommendationEventMetadata = Field(default_factory=RecommendationEventMetadata)


ChatResponse.model_rebuild()
