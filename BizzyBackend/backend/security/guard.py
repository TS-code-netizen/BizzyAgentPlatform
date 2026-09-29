from __future__ import annotations

from backend.models.agent import AgentResponse


READ_ONLY_TYPES = {
    "monitor_sales_trend", "monitor_stock_levels", "review_sales_analysis",
    "investigate_stock_availability", "review_product_performance", "review_inventory_analysis",
    "prioritise_top_seller_replenishment", "review_slow_moving_inventory",
    "prioritise_revenue_recovery", "review_advisor_summary",
}
APPROVAL_TYPES = {
    "prepare_purchase_order", "verify_inbound_quantity", "review_purchase_order_bundle",
    "prepare_customer_follow_up", "review_supplier_quality_defect", "prepare_invoice_reminders",
}


def action_decision(action) -> str:
    if action.risk_level.value == "RED" or action.type not in READ_ONLY_TYPES | APPROVAL_TYPES:
        return "blocked"
    if _invalid_controlled_action(action.type, action.parameters):
        return "blocked"
    if action.type in APPROVAL_TYPES or action.risk_level.value == "AMBER":
        return "approval_required"
    return "allowed"


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _invalid_controlled_action(action_type: str, parameters: dict[str, object]) -> bool:
    if action_type == "prepare_purchase_order":
        return not (
            parameters.get("product_id")
            and parameters.get("supplier_id")
            and _positive_integer(parameters.get("quantity"))
        )
    if action_type == "verify_inbound_quantity":
        return not (
            parameters.get("product_id")
            and parameters.get("supplier_id")
            and parameters.get("existing_receipt_date")
            and _positive_integer(parameters.get("provisional_additional_order_qty"))
        )
    if action_type == "review_purchase_order_bundle":
        product_ids = parameters.get("product_ids")
        return not (
            isinstance(product_ids, list)
            and product_ids
            and all(isinstance(product_id, str) and product_id for product_id in product_ids)
            and _positive_integer(parameters.get("total_suggested_units"))
        )
    return False


def evaluate(actions_from_agents: list[AgentResponse]) -> tuple[str, bool]:
    all_actions = [action for response in actions_from_agents for action in response.recommended_actions]
    decisions = [action_decision(action) for action in all_actions]
    if "blocked" in decisions:
        return "blocked", True
    if "approval_required" in decisions:
        return "approval_required", True
    return "allowed", False
