from app.models.schemas import SessionStateResponse
from app.services.session_store import session_store


def session_response(session_id: str) -> SessionStateResponse:
    return SessionStateResponse(
        session_id=session_id,
        wishlist=session_store.get_wishlist(session_id),
        cart=session_store.get_cart(session_id),
        viewed=session_store.get_viewed(session_id),
        wishlist_ids=session_store.get_wishlist_ids(session_id),
        cart_ids=session_store.get_cart_ids(session_id),
        viewed_ids=session_store.get_viewed_ids(session_id),
    )
