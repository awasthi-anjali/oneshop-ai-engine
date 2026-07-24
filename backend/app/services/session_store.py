import time
import uuid

from app.models.schemas import Product
from app.services.product_catalog import catalog

ABANDONMENT_THRESHOLD_SEC = 30  # demo: 30s inactive = abandoned


class SessionStore:
    def __init__(self) -> None:
        self._wishlists: dict[str, set[str]] = {}
        self._carts: dict[str, set[str]] = {}
        self._viewed: dict[str, list[str]] = {}
        self._cart_updated_at: dict[str, float] = {}
        self._abandoned: dict[str, bool] = {}
        self._recovery_discount: dict[str, float] = {}
        self._orders: dict[str, list[dict]] = {}
        # Omnichannel: customer identity + channel tracking
        self._customer_to_session: dict[str, str] = {}
        self._session_to_customer: dict[str, str] = {}
        self._last_channel: dict[str, str] = {}
        self._channels_used: dict[str, set[str]] = {}

    def get_or_create(self, session_id: str | None) -> str:
        sid = session_id or str(uuid.uuid4())
        self._wishlists.setdefault(sid, set())
        self._carts.setdefault(sid, set())
        self._viewed.setdefault(sid, [])
        self._cart_updated_at.setdefault(sid, time.time())
        self._abandoned.setdefault(sid, False)
        self._recovery_discount.setdefault(sid, 0.0)
        self._orders.setdefault(sid, [])
        return sid

    def _touch_cart(self, session_id: str) -> None:
        self._cart_updated_at[session_id] = time.time()
        self._abandoned[session_id] = False
        self._recovery_discount[session_id] = 0.0

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
        return list(self._carts.get(session_id, set()))

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
        self._carts[session_id].add(product_id)
        self._touch_cart(session_id)
        return list(self._carts[session_id])

    def add_bundle_to_cart(self, session_id: str, product_ids: list[str]) -> list[str]:
        self.get_or_create(session_id)
        for pid in product_ids:
            if catalog.get_by_id(pid):
                self._carts[session_id].add(pid)
        self._touch_cart(session_id)
        return list(self._carts[session_id])

    def remove_from_cart(self, session_id: str, product_id: str) -> list[str]:
        self.get_or_create(session_id)
        self._carts[session_id].discard(product_id)
        self._touch_cart(session_id)
        return list(self._carts[session_id])

    def clear_cart(self, session_id: str) -> None:
        self._carts[session_id] = set()
        self._abandoned[session_id] = False
        self._recovery_discount[session_id] = 0.0

    def toggle_cart(self, session_id: str, product_id: str) -> tuple[bool, list[str]]:
        self.get_or_create(session_id)
        cart = self._carts[session_id]
        if product_id in cart:
            cart.remove(product_id)
            added = False
        else:
            cart.add(product_id)
            added = True
        self._touch_cart(session_id)
        return added, list(cart)

    def mark_abandoned(self, session_id: str) -> bool:
        self.get_or_create(session_id)
        if not self._carts[session_id]:
            return False
        self._abandoned[session_id] = True
        self._recovery_discount[session_id] = 10.0  # 10% recovery offer
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
                self._recovery_discount[session_id] = 10.0
                discount = 10.0

        recovery_message = ""
        if is_abandoned and cart:
            recovery_message = (
                f"Welcome back! You left {len(cart)} item(s) in your cart. "
                f"Complete checkout now for {discount:.0f}% off!"
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

    def record_order(self, session_id: str, order: dict) -> str:
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order["order_id"] = order_id
        self._orders[session_id].append(order)
        return order_id

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

        self._carts[target] = self._carts.get(target, set()) | self._carts.get(source, set())
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

        self._orders[target].extend(self._orders.get(source, []))

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
