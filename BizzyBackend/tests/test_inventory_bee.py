from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.agents.inventory import inventory_bee
from backend.models.agent import AgentResponse, AgentStatus, RiskLevel
from backend.tools.inventory_tools import StockRisk, assess_inventory, simulate_reorder

AS_OF = date(2026, 9, 23)
INVENTORY_HEADER = (
    "product_id,product,current_stock,reorder_level,lead_time,supplier_id,supplier,"
    "next_expected_receipt_date,stock_value"
)
HISTORY_HEADER = "date,product_id,units_sold,unfulfilled_demand"
PRODUCTS_HEADER = "product_id,unit_price"


def evidence_map(response: AgentResponse) -> dict[str, object]:
    return {item.metric: item.value for item in response.evidence}


def product(status, product_id: str):
    return next(item for item in status.products if item.product_id == product_id)


def test_risk_uses_days_of_cover_not_reorder_level(fixture_data_dir) -> None:
    status = assess_inventory(fixture_data_dir, AS_OF)
    prd003 = product(status, "PRD003")

    assert {item.product_id: item.risk for item in status.products} == {
        "PRD001": StockRisk.OUT_OF_STOCK,
        "PRD002": StockRisk.AT_RISK,
        "PRD003": StockRisk.OK,
    }
    # PRD003 sits exactly on its reorder level, but 6 days of cover exceed its 5-day lead time.
    assert prd003.current_stock == prd003.reorder_level
    assert prd003.days_of_cover == 6.0


def test_out_of_stock_product_quantifies_lost_and_projected_sales(fixture_data_dir) -> None:
    focus = assess_inventory(fixture_data_dir, AS_OF).focus

    assert focus is not None
    assert focus.product_id == "PRD001"
    assert focus.avg_daily_demand == 3.0
    assert focus.recent_unfulfilled_units == 21
    assert focus.recent_lost_revenue == Decimal("2100.00")
    assert focus.first_recent_unfulfilled_date == date(2026, 9, 17)
    assert focus.days_until_restock(AS_OF) == 4
    assert focus.projected_lost_revenue(AS_OF) == Decimal("1200")
    assert focus.suggested_order_qty == 42


def test_reorder_simulation_supports_demand_uplift(fixture_data_dir) -> None:
    focus = assess_inventory(fixture_data_dir, AS_OF).focus
    assert focus is not None

    simulation = simulate_reorder(focus, AS_OF, demand_uplift_pct=20)

    assert simulation.order_qty == 45
    assert simulation.effective_daily_demand == 3.6
    assert simulation.expected_lost_units_before_receipt == 14.4
    assert simulation.expected_lost_revenue_before_receipt == Decimal("1440.000000")
    assert round(simulation.days_of_cover_after_receipt or 0, 1) == 12.5


def test_known_incoming_quantity_reduces_purchase_order(write_csv) -> None:
    write_csv(
        "inventory.csv",
        "product_id,product,current_stock,reorder_level,lead_time,supplier_id,supplier,"
        "next_expected_receipt_date,incoming_qty,stock_value",
        "PRD001,Product A,0,30,4,SUP001,Demo Supplier 01,2026-09-28,20,0.00",
    )
    write_csv("products.csv", PRODUCTS_HEADER, "PRD001,100.00")
    data_dir = write_csv(
        "inventory_history.csv",
        HISTORY_HEADER,
        "2026-09-22,PRD001,0,3",
        "2026-09-23,PRD001,0,3",
    )

    response = inventory_bee(
        question="Should we place a purchase order for PRD001?",
        as_of=AS_OF,
        data_dir=data_dir,
    )
    evidence = evidence_map(response)
    action = response.recommended_actions[0]

    assert evidence["incoming_qty"] == 20
    assert evidence["suggested_order_qty"] == 22
    assert evidence["suggested_order_qty_is_provisional"] is False
    assert action.type == "prepare_purchase_order"
    assert action.parameters["quantity"] == 22
    assert action.parameters["existing_receipt_date"] == "2026-09-28"
    assert action.parameters["proposed_order_earliest_arrival"] == "2026-09-27"


def test_at_risk_product_order_covers_lead_time_demand(fixture_data_dir) -> None:
    prd002 = product(assess_inventory(fixture_data_dir, AS_OF), "PRD002")

    assert prd002.days_of_cover == 2.4
    assert prd002.projected_lost_units(AS_OF) == 0.0
    assert prd002.suggested_order_qty == 35


def test_inventory_ranks_sellers_stock_value_and_supplier_lead_times(fixture_data_dir) -> None:
    status = assess_inventory(fixture_data_dir, AS_OF)

    assert [(item.product_id, item.avg_daily_units_sold) for item in status.top_sellers(10)] == [
        ("PRD003", 10.0),
        ("PRD002", 5.0),
        ("PRD001", 1.5),
    ]
    assert [item.product_id for item in status.highest_stock_value(2)] == ["PRD003", "PRD002"]
    assert status.longest_lead_time_suppliers(2) == [("Demo Supplier 02", 7), ("Demo Supplier 03", 5)]
    assert [item.product_id for item in status.reorder_candidates] == ["PRD001", "PRD002"]
    assert status.total_suggested_order_units == 77


def test_inventory_bee_returns_contract_with_evidence(fixture_data_dir) -> None:
    response = inventory_bee(as_of=AS_OF, data_dir=fixture_data_dir)
    evidence = evidence_map(response)

    AgentResponse.model_validate(response.model_dump())
    assert response.agent == "inventory"
    assert response.status is AgentStatus.SUCCESS
    assert response.confidence == 0.95
    assert evidence["out_of_stock_products"] == "PRD001"
    assert evidence["at_risk_products"] == "PRD002"
    assert evidence["at_risk_stock_units"] == "PRD002: 12"
    assert evidence["reorder_candidate_count"] == 2
    assert evidence["total_suggested_order_units"] == 77
    assert evidence["top_sellers_at_risk_count"] == 2
    assert evidence["top_sellers_stock_cover"].startswith(
        "PRD003: 10.0 units/day sold, 60 in stock, 6.0 days of cover (ok)"
    )
    assert evidence["highest_stock_value_products"].startswith("PRD003 Insulated Bottle Model 03: SGD 1,800.00")
    assert evidence["longest_lead_time_suppliers"] == "Demo Supplier 02: 7 days | Demo Supplier 03: 5 days | Demo Supplier 01: 4 days"
    assert evidence["product_id"] == "PRD001"
    assert evidence["current_stock"] == 0
    assert evidence["recent_unfulfilled_demand_units"] == 21
    assert evidence["recent_lost_revenue_sgd"] == 2100.0
    assert evidence["projected_lost_revenue_sgd_until_restock"] == 1200.0
    assert evidence["next_expected_receipt_date"] == "2026-09-28"
    assert evidence["incoming_qty_status"] == "unknown"
    assert evidence["suggested_order_qty"] == 42
    assert evidence["suggested_order_qty_is_provisional"] is True
    assert evidence["at_or_below_reorder_product_count"] == 3
    assert evidence["stock_risk_details"][0]["projected_stockout_date"] == "2026-09-23"
    assert evidence["top_seller_stock_details"][0]["product_id"] == "PRD003"
    assert evidence["inventory_value_details"][0]["product_id"] == "PRD003"
    assert [(action.type, action.risk_level) for action in response.recommended_actions] == [
        ("verify_inbound_quantity", RiskLevel.AMBER)
    ]
    assert response.summary.endswith("1 other product may run out before replenishment arrives.")


def test_inventory_bee_selects_valuation_analysis_for_question(fixture_data_dir) -> None:
    response = inventory_bee(
        question="What is the total FIFO stock valuation right now?",
        as_of=AS_OF,
        data_dir=fixture_data_dir,
    )
    evidence = evidence_map(response)

    assert evidence["total_stock_value_sgd"] == 2376.0
    assert "product_id" not in evidence
    assert "out_of_stock_products" not in evidence
    assert response.recommended_actions[0].risk_level is RiskLevel.GREEN


def test_inventory_bee_returns_what_if_analysis_and_purchase_order(fixture_data_dir) -> None:
    response = inventory_bee(
        question="What if demand increases by 20% for PRD001?",
        as_of=AS_OF,
        data_dir=fixture_data_dir,
    )
    evidence = evidence_map(response)
    action = response.recommended_actions[0]

    assert evidence["simulation_demand_uplift_pct"] == 20.0
    assert evidence["simulation_expected_lost_revenue_before_receipt_sgd"] == 1440.0
    assert evidence["simulation_days_of_cover_after_receipt"] == 12.5
    assert action.risk_level is RiskLevel.AMBER
    assert action.type == "verify_inbound_quantity"
    assert action.parameters["product_id"] == "PRD001"
    assert action.parameters["provisional_additional_order_qty"] == 45
    assert action.expected_impact["demand_uplift_pct"] == 20.0


def test_product_specific_question_does_not_reorder_healthy_stock(fixture_data_dir) -> None:
    response = inventory_bee(
        question="How many PRD003 units are left?",
        as_of=AS_OF,
        data_dir=fixture_data_dir,
    )
    evidence = evidence_map(response)

    assert evidence["product_id"] == "PRD003"
    assert evidence["stock_risk"] == "ok"
    assert response.recommended_actions[0].type == "monitor_stock_levels"
    assert response.recommended_actions[0].risk_level is RiskLevel.GREEN


def test_healthy_inventory_recommends_monitoring(write_csv) -> None:
    write_csv("inventory.csv", INVENTORY_HEADER, "PRD003,Insulated Bottle Model 03,100,10,5,SUP003,Demo Supplier 03,,3000.00")
    write_csv("products.csv", PRODUCTS_HEADER, "PRD003,50.00")
    data_dir = write_csv("inventory_history.csv", HISTORY_HEADER, "2026-09-22,PRD003,2,0", "2026-09-23,PRD003,2,0")

    response = inventory_bee(as_of=AS_OF, data_dir=data_dir)

    assert response.status is AgentStatus.SUCCESS
    assert evidence_map(response)["out_of_stock_product_count"] == 0
    assert "product_id" not in evidence_map(response)
    assert [(action.type, action.risk_level) for action in response.recommended_actions] == [
        ("monitor_stock_levels", RiskLevel.GREEN)
    ]


def test_inventory_without_recent_history_is_partial(write_csv) -> None:
    write_csv("inventory.csv", INVENTORY_HEADER, "PRD003,Insulated Bottle Model 03,5,10,5,SUP003,Demo Supplier 03,,150.00")
    write_csv("products.csv", PRODUCTS_HEADER, "PRD003,50.00")
    data_dir = write_csv("inventory_history.csv", HISTORY_HEADER, "2026-08-01,PRD003,2,0")

    response = inventory_bee(as_of=AS_OF, data_dir=data_dir)

    assert response.status is AgentStatus.PARTIAL
    assert response.confidence == 0.6


def test_inventory_bee_fails_gracefully_when_files_missing(write_csv) -> None:
    data_dir = write_csv("inventory.csv", INVENTORY_HEADER, "PRD001,Product A,0,30,4,SUP001,Demo Supplier 01,,0.00")

    response = inventory_bee(as_of=AS_OF, data_dir=data_dir)

    assert response.status is AgentStatus.FAILED
    assert response.confidence == 0.0
    assert response.recommended_actions == []
