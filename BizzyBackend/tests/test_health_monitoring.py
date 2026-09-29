from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.agent import RiskLevel
from backend.models.health import AlertSeverity
from backend.tools import demo_data
from backend.tools.health_tools import build_sales_inventory_health

AS_OF = date(2026, 9, 23)
client = TestClient(app)


def test_health_engine_scores_revenue_and_inventory_risk(fixture_data_dir) -> None:
    health = build_sales_inventory_health(fixture_data_dir, AS_OF)

    assert health.score == 53
    assert health.status == "at_risk"
    assert health.score_breakdown == {
        "revenue_trend_penalty": 25.0,
        "stockout_penalty": 15.0,
        "stock_risk_penalty": 6.7,
        "data_coverage_penalty": 0.0,
    }
    assert health.metrics["recent_lost_revenue_sgd"] == 2100.0
    assert health.metrics["projected_lost_revenue_until_restock_sgd"] == 1200.0


def test_health_engine_creates_actionable_alerts(fixture_data_dir) -> None:
    alerts = build_sales_inventory_health(fixture_data_dir, AS_OF).priority_issues
    alert_types = [alert.alert_type for alert in alerts]

    assert alert_types[:2] == ["revenue_decline", "stockout"]
    assert "stockout_risk" in alert_types
    stockout = next(alert for alert in alerts if alert.alert_type == "stockout")
    assert stockout.severity is AlertSeverity.CRITICAL
    assert stockout.product_id == "PRD001"
    assert stockout.recommended_action is not None
    assert stockout.recommended_action.risk_level is RiskLevel.AMBER
    assert stockout.recommended_action.type == "verify_inbound_quantity"
    assert stockout.recommended_action.parameters["provisional_additional_order_qty"] == 42
    assert stockout.recommended_action.parameters["existing_receipt_date"] == "2026-09-28"


def test_health_engine_warns_when_source_coverage_is_incomplete(write_csv) -> None:
    write_csv(
        "sales.csv",
        "date,product_id,product,quantity,revenue,cost_of_goods_sold,channel",
        "2026-09-16,PRD003,Insulated Bottle Model 03,2,100.00,50.00,web",
        "2026-09-23,PRD003,Insulated Bottle Model 03,3,150.00,75.00,web",
    )
    write_csv(
        "inventory.csv",
        "product_id,product,current_stock,reorder_level,lead_time,supplier_id,supplier,"
        "next_expected_receipt_date,stock_value",
        "PRD003,Insulated Bottle Model 03,100,10,5,SUP003,Demo Supplier 03,,3000.00",
    )
    write_csv(
        "products.csv",
        "product_id,product,category,supplier_id,unit_price,unit_cost",
        "PRD003,Insulated Bottle Model 03,Outdoor,SUP003,50.00,25.00",
    )
    data_dir = write_csv(
        "inventory_history.csv",
        "date,product_id,units_sold,unfulfilled_demand",
        "2026-09-22,PRD003,2,0",
        "2026-09-23,PRD003,2,0",
    )

    health = build_sales_inventory_health(data_dir, AS_OF)

    assert health.status == "healthy"
    assert all(alert.alert_type not in {"revenue_decline", "stockout", "stockout_risk"} for alert in health.priority_issues)
    coverage = next(alert for alert in health.priority_issues if alert.alert_type == "data_quality")
    assert coverage.severity is AlertSeverity.WARNING
    assert coverage.current_value < coverage.threshold


def test_health_and_alert_endpoints_return_live_analysis() -> None:
    legacy_response = client.get("/api/v1/business-health")
    health_response = client.get("/api/v1/sales-inventory/health")
    alerts_response = client.get("/api/v1/sales-inventory/alerts")

    assert legacy_response.status_code == 200
    assert legacy_response.json()["score"] == 53
    assert legacy_response.json()["status"] == "at_risk"
    assert health_response.status_code == 200
    health = health_response.json()
    assert health["score"] == 53
    assert health["metrics"]["out_of_stock_product_count"] == 1

    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert any(alert["alert_type"] == "stockout" and alert["product_id"] == "PRD001" for alert in alerts)


def test_health_endpoint_returns_503_when_sources_are_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo_data, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/sales-inventory/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "Sales or inventory data is unavailable or invalid."

