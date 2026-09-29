from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def evidence_map(body: dict) -> dict[str, object]:
    return {item["metric"]: item["value"] for item in body["evidence"]}


def test_sales_summary_endpoint_returns_agent_contract() -> None:
    response = client.get("/api/v1/sales/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "sales"
    assert body["status"] == "success"
    assert evidence_map(body)["revenue_change_pct"] == -25.0
    assert evidence_map(body)["recent_period"] == "2026-09-17/2026-09-23"


def test_sales_summary_accepts_custom_as_of_date() -> None:
    response = client.get("/api/v1/sales/summary", params={"as_of": "2026-09-16"})

    assert response.status_code == 200
    evidence = evidence_map(response.json())
    assert evidence["recent_period"] == "2026-09-10/2026-09-16"
    assert evidence["recent_revenue_sgd"] == 8400.0


def test_summary_endpoints_accept_question_specific_analysis() -> None:
    sales_response = client.get(
        "/api/v1/sales/summary",
        params={"question": "Which channel generated the most revenue?"},
    )
    inventory_response = client.get(
        "/api/v1/inventory/status",
        params={"question": "What if demand increases by 20% for PRD001?"},
    )

    assert sales_response.status_code == 200
    assert evidence_map(sales_response.json())["top_channel"] == "marketplace"
    assert inventory_response.status_code == 200
    assert evidence_map(inventory_response.json())["simulation_demand_uplift_pct"] == 20.0


def test_chinese_overview_summaries_prioritise_revenue_and_stock_risk() -> None:
    sales_response = client.get("/api/v1/sales/summary", params={"language": "zh-CN"})
    inventory_response = client.get("/api/v1/inventory/status", params={"language": "zh-CN"})

    assert "下降 25.0%" in sales_response.json()["summary"]
    assert "渠道收入最高" not in sales_response.json()["summary"]
    assert "1 个断货商品" in inventory_response.json()["summary"]
    assert "交期最长" not in inventory_response.json()["summary"]


def test_finance_summary_endpoint_returns_live_overdue_receivables() -> None:
    response = client.get("/api/v1/finance/summary", params={"language": "zh-CN"})

    assert response.status_code == 200
    body = response.json()
    evidence = evidence_map(body)
    assert evidence["overdue_invoice_count"] == 2
    assert evidence["overdue_outstanding_sgd"] == 280.0
    assert "2 张逾期发票" in body["summary"]


def test_inventory_status_endpoint_returns_agent_contract() -> None:
    response = client.get("/api/v1/inventory/status")

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "inventory"
    assert body["status"] == "success"
    assert evidence_map(body)["product_id"] == "PRD001"
    action = body["recommended_actions"][0]
    assert action["type"] == "verify_inbound_quantity"
    assert action["risk_level"] == "AMBER"
    assert action["parameters"]["product_id"] == "PRD001"
    assert action["parameters"]["provisional_additional_order_qty"] == 42
    assert action["expected_impact"]["decision_blocked_until"] == "incoming_quantity_verified"


def test_endpoints_validate_window_days() -> None:
    assert client.get("/api/v1/sales/summary", params={"window_days": 0}).status_code == 422
    assert client.get("/api/v1/inventory/status", params={"window_days": 91}).status_code == 422
