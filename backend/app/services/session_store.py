import time
import uuid

from app.models.schemas import Product
from app.services.commerce_store import commerce_store
from app.services.product_catalog import catalog

ABANDONMENT_THRESHOLD_SEC = 30  # demo: 30s inactive = abandoned


class SessionStore:
    def __init__(self) -> None:
        self._wishlists: dict[str, set[str]] = {}
        self._viewed: dict[str, list[str]] = {}
        self._cart_updated_at: dict[str, float] = {}
        self._abandoned: dict[str, bool] = {}
        self._recovery_discount: dict[str, float] = {}
        # Omnichannel: customer identity + channel tracking
        self._customer_to_session: dict[str, str] = {}
        self._session_to_customer: dict[str, str] = {}
        self._last_channel: dict[str, str] = {}
        self._channels_used: dict[str, set[str]] = {}
        self._last_cart_add: dict[str, str] = {}

    def get_or_create(self, session_id: str | None) -> str:
        sid = session_id or str(uuid.uuid4())
        self._wishlists.setdefault(sid, set())
        self._viewed.setdefault(sid, [])
        self._cart_updated_at.setdefault(sid, time.time())
        self._abandoned.setdefault(sid, False)
        self._recovery_discount.setdefault(sid, 0.0)
        commerce_store.ensure_cart(sid)
        return sid

    def _touch_cart(self, session_id: str) -> None:
        self._cart_updated_at[session_id] = time.time()
        self._abandoned[session_id] = False

    def get_viewed_ids(self, session_id: str) -> list[str]:
        return list(self._viewed.get(session_id, []))

    def get_viewed(self, session_id: str) -> list[Product]:
        return catalog.get_by_ids(self.get_viewed_ids(session_id))

    def track_view(self, session_id: str, product_id: str) -> list[str]:
        self.get_or_create(session_id)
        viewed = self._viewed[session_id]
        if product_id in viewed:
            viewed.remove(product_id)
        viewed.insert(0, product_id)
        self._viewed[session_id] = viewed[:20]
        return list(self._viewed[session_id])

    def get_wishlist_ids(self, session_id: str) -> list[str]:
        return list(self._wishlists.get(session_id, set()))

    def get_cart_ids(self, session_id: str) -> list[str]:
        return commerce_store.cart_ids(session_id)

    def get_wishlist(self, session_id: str) -> list[Product]:
        return catalog.get_by_ids(self.get_wishlist_ids(session_id))

    def get_cart(self, session_id: str) -> list[Product]:
        return catalog.get_by_ids(self.get_cart_ids(session_id))

    def toggle_wishlist(self, session_id: str, product_id: str) -> tuple[bool, list[str]]:
        self.get_or_create(session_id)
        wishlist = self._wishlists[session_id]
        if product_id in wishlist:
            wishlist.remove(product_id)
            added = False
        else:
            wishlist.add(product_id)
            added = True
        return added, list(wishlist)

    def add_to_cart(self, session_id: str, product_id: str) -> list[str]:
        self.get_or_create(session_id)
        cart_ids = commerce_store.add_items(session_id, [product_id])
        self._last_cart_add[session_id] = product_id
        self._touch_cart(session_id)
        return cart_ids

    def get_last_cart_add(self, session_id: str) -> str | None:
        return self._last_cart_add.get(session_id)

    def add_bundle_to_cart(self, session_id: str, product_ids: list[str]) -> list[str]:
        self.get_or_create(session_id)
        cart_ids = commerce_store.add_items(session_id, product_ids)
        if product_ids:
            self._last_cart_add[session_id] = product_ids[-1]
        self._touch_cart(session_id)
        return cart_ids

    def remove_from_cart(self, session_id: str, product_id: str) -> list[str]:
        self.get_or_create(session_id)
        cart_ids = commerce_store.remove_items(session_id, [product_id])
        self._touch_cart(session_id)
        return cart_ids

    def clear_cart(self, session_id: str) -> None:
        commerce_store.clear_cart(session_id)
        self._abandoned[session_id] = False
        self._recovery_discount[session_id] = 0.0

    def toggle_cart(self, session_id: str, product_id: str) -> tuple[bool, list[str]]:
        self.get_or_create(session_id)
        added, cart_ids = commerce_store.toggle_item(session_id, product_id)
        self._touch_cart(session_id)
        return added, cart_ids

    def mark_abandoned(self, session_id: str) -> bool:
        self.get_or_create(session_id)
        if not self.get_cart_ids(session_id):
            return False
        self._abandoned[session_id] = True
        self._recovery_discount[session_id] = 0.0
        return True

    def get_abandonment_status(self, session_id: str) -> dict:
        self.get_or_create(session_id)
        cart = self.get_cart(session_id)
        is_abandoned = self._abandoned.get(session_id, False)
        discount = self._recovery_discount.get(session_id, 0.0)

        if cart and not is_abandoned:
            elapsed = time.time() - self._cart_updated_at.get(session_id, time.time())
            if elapsed >= ABANDONMENT_THRESHOLD_SEC:
                is_abandoned = True
                self._abandoned[session_id] = True
                self._recovery_discount[session_id] = 0.0
                discount = 0.0

        recovery_message = ""
        if is_abandoned and cart:
            item_label = "item" if len(cart) == 1 else "items"
            recovery_message = (
                f"Welcome back! You left {len(cart)} {item_label} in your cart. "
                "Your selections are ready when you are."
            )

        return {
            "is_abandoned": is_abandoned and bool(cart),
            "recovery_message": recovery_message,
            "discount_offer": discount if is_abandoned else 0.0,
            "cart_count": len(cart),
        }

    def clear_abandonment(self, session_id: str) -> None:
        self._abandoned[session_id] = False
        self._recovery_discount[session_id] = 0.0

    def get_recovery_discount(self, session_id: str) -> float:
        return self._recovery_discount.get(session_id, 0.0)

    def record_channel(self, session_id: str, channel: str) -> None:
        self.get_or_create(session_id)
        ch = channel if channel in ("oneshop", "oneapp") else "oneshop"
        self._last_channel[session_id] = ch
        self._channels_used.setdefault(session_id, set()).add(ch)

    def get_channel_info(self, session_id: str) -> dict:
        self.get_or_create(session_id)
        used = sorted(self._channels_used.get(session_id, set()))
        last = self._last_channel.get(session_id, "")
        other = next((c for c in used if c != last), None)
        return {
            "current_channel": last,
            "last_channel": last,
            "channels_used": used,
            "is_cross_channel": len(used) > 1,
            "other_channel": other,
        }

    def _merge_sessions(self, source: str, target: str) -> None:
        if source == target:
            return
        self.get_or_create(source)
        self.get_or_create(target)

        commerce_store.merge_carts(source, target)
        self._wishlists[target] = self._wishlists.get(target, set()) | self._wishlists.get(source, set())

        merged_viewed = list(self._viewed.get(source, []))
        for vid in self._viewed.get(target, []):
            if vid not in merged_viewed:
                merged_viewed.append(vid)
        self._viewed[target] = merged_viewed[:20]

        self._cart_updated_at[target] = max(
            self._cart_updated_at.get(target, 0),
            self._cart_updated_at.get(source, 0),
        )

        if self._abandoned.get(source):
            self._abandoned[target] = True
            self._recovery_discount[target] = max(
                self._recovery_discount.get(target, 0),
                self._recovery_discount.get(source, 0),
            )

        source_channels = self._channels_used.get(source, set())
        self._channels_used.setdefault(target, set()).update(source_channels)

        if source in self._last_channel:
            if (
                target not in self._last_channel
                or self._cart_updated_at.get(source, 0) >= self._cart_updated_at.get(target, 0)
            ):
                self._last_channel[target] = self._last_channel[source]

        if source in self._session_to_customer:
            del self._session_to_customer[source]

    def link_customer(self, customer_id: str, session_id: str | None = None) -> str:
        if customer_id in self._customer_to_session:
            existing_sid = self._customer_to_session[customer_id]
            if session_id:
                current_sid = self.get_or_create(session_id)
                if current_sid != existing_sid:
                    self._merge_sessions(current_sid, existing_sid)
            return existing_sid
        sid = self.get_or_create(session_id)
        self._customer_to_session[customer_id] = sid
        self._session_to_customer[sid] = customer_id
        return sid

    def get_customer_id(self, session_id: str) -> str | None:
        return self._session_to_customer.get(session_id)

    def resolve_session(
        self,
        session_id: str | None = None,
        customer_id: str | None = None,
    ) -> str:
        if customer_id and customer_id in self._customer_to_session:
            existing_sid = self._customer_to_session[customer_id]
            if session_id:
                current_sid = self.get_or_create(session_id)
                if current_sid != existing_sid:
                    self._merge_sessions(current_sid, existing_sid)
            return existing_sid
        return self.get_or_create(session_id)


session_store = SessionStore()
