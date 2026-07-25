from app.models.schemas import CartProposal
from app.services.cart_proposal_store import CartProposalStore
from app.services.product_catalog import catalog
from app.services.session_store import SessionStore


def test_add_bundle_to_cart_updates_last_cart_add():
    store = SessionStore()
    sid = store.get_or_create(None)
    store.add_bundle_to_cart(sid, ["iphone-15-pro", "unlimited-plus"])

    assert store.get_last_cart_add(sid) == "unlimited-plus"


def test_cart_proposal_persists_across_store_instances(tmp_path):
    db_path = tmp_path / "cart_proposals.sqlite3"
    phone = catalog.get_by_id("google-pixel-8")
    assert phone is not None

    proposal = CartProposal(
        proposal_id="proposal-test-1234567890",
        products=[phone],
        product_ids=[phone.id],
        excluded_product_ids=[],
        one_time_total=phone.price,
        monthly_total=0,
    )

    store_a = CartProposalStore(db_path)
    store_a.save(proposal.proposal_id, "session-a", "user_a", proposal)

    store_b = CartProposalStore(db_path)
    loaded = store_b.get(proposal.proposal_id)

    assert loaded is not None
    assert loaded.session_id == "session-a"
    assert loaded.user_id == "user_a"
    assert loaded.proposal.product_ids == [phone.id]
