from app.models.schemas import NextBestAction
from app.services.next_best_action_service import sanitize_next_best_actions


def test_ai_checkout_copy_is_backend_owned_and_demo_safe() -> None:
    actions = sanitize_next_best_actions(
        [
            {
                "action": "complete_purchase_checkout",
                "label": "Secure checkout and save $15",
                "priority": 1,
            }
        ]
    )

    assert actions == [
        NextBestAction(
            action="checkout",
            label="Start demo checkout",
            priority=1,
        )
    ]


def test_unknown_or_duplicate_ai_actions_cannot_inject_labels() -> None:
    actions = sanitize_next_best_actions(
        [
            {"action": "free_phone_offer", "label": "Claim a free phone", "priority": "bad"},
            {"action": "explore", "label": "Guaranteed discount", "priority": 2},
            {"action": "add_plan", "label": "Save $15 per month", "priority": 3},
        ]
    )

    assert [(action.action, action.label) for action in actions] == [
        ("explore", "Explore products"),
        ("add_plan", "Compare plan options"),
    ]


def test_existing_actions_are_resanitized() -> None:
    actions = sanitize_next_best_actions(
        [
            NextBestAction(
                action="checkout",
                label="Payment successful",
                priority=1,
            )
        ]
    )

    assert actions[0].label == "Start demo checkout"
