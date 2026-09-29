from __future__ import annotations

from backend.models.agent import AgentResponse, AgentStatus, RecommendedAction, RiskLevel
from backend.security.guard import evaluate


def response_with(action: RecommendedAction) -> AgentResponse:
    return AgentResponse(
        agent="test",
        status=AgentStatus.SUCCESS,
        summary="test",
        confidence=1.0,
        recommended_actions=[action],
    )


def test_guard_requires_approval_for_controlled_action_even_if_marked_green() -> None:
    action = RecommendedAction(
        type="prepare_purchase_order",
        risk_level=RiskLevel.GREEN,
        parameters={"product_id": "PRD001", "supplier_id": "SUP001", "quantity": 10},
    )

    assert evaluate([response_with(action)]) == ("approval_required", True)


def test_guard_blocks_purchase_order_with_invalid_parameters() -> None:
    action = RecommendedAction(
        type="prepare_purchase_order",
        risk_level=RiskLevel.AMBER,
        parameters={"product_id": "PRD001", "supplier_id": "SUP001", "quantity": 0},
    )

    assert evaluate([response_with(action)]) == ("blocked", True)


def test_guard_validates_inbound_verification_action() -> None:
    action = RecommendedAction(
        type="verify_inbound_quantity",
        risk_level=RiskLevel.AMBER,
        parameters={
            "product_id": "PRD001",
            "supplier_id": "SUP001",
            "existing_receipt_date": "2026-09-28",
            "provisional_additional_order_qty": 42,
        },
    )

    assert evaluate([response_with(action)]) == ("approval_required", True)


def test_guard_allows_non_controlled_green_action() -> None:
    action = RecommendedAction(type="monitor_sales_trend", risk_level=RiskLevel.GREEN)

    assert evaluate([response_with(action)]) == ("allowed", False)

