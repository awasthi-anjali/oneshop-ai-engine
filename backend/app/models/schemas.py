from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str
    products: list[Product] = Field(default_factory=list)
    comparison: list[Product] | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    channel: str = "oneshop"  # oneshop | oneapp


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    suggested_actions: list[str] = Field(default_factory=list)
    cart_updated: bool = False
    open_checkout: bool = False


class ProductSearchRequest(BaseModel):
    query: str = ""
    category: ProductCategory | None = None
    max_price: float | None = None
    min_price: float | None = None
    brand: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = 10


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
    savings: float
    reason: str


class SmartCartResponse(BaseModel):
    session_id: str
    cart: list[Product] = Field(default_factory=list)
    bundles: list[BundleSuggestion] = Field(default_factory=list)
    nudge: str = ""
    checkout_tip: str = ""
    ai_powered: bool = False
    subtotal: float = 0
    estimated_savings: float = 0


class BundleAddRequest(BaseModel):
    session_id: str | None = None
    product_ids: list[str] = Field(..., min_length=1)


class CheckoutRequest(BaseModel):
    session_id: str | None = None
    customer_name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=3)
    payment_last4: str = Field(default="4242", min_length=4, max_length=4)


class CheckoutResponse(BaseModel):
    session_id: str
    order_id: str
    items: list[Product] = Field(default_factory=list)
    subtotal: float
    savings: float
    discount: float = 0
    total: float
    message: str


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
    nudge: str = ""
    checkout_tip: str = ""
    subtotal: float = 0
    estimated_savings: float = 0
    ai_powered: bool = False
    abandonment: AbandonmentResponse | None = None


class SessionStateResponse(BaseModel):
    session_id: str
    wishlist: list[Product] = Field(default_factory=list)
    cart: list[Product] = Field(default_factory=list)
    viewed: list[Product] = Field(default_factory=list)
    wishlist_ids: list[str] = Field(default_factory=list)
    cart_ids: list[str] = Field(default_factory=list)
    viewed_ids: list[str] = Field(default_factory=list)


class SessionActionRequest(BaseModel):
    session_id: str | None = None
    product_id: str
