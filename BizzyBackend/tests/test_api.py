from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_routes_are_registered_once() -> None:
    def leaf_routes(routes):
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                yield from leaf_routes(included.routes)
            else:
                yield route

    registered = [
        (route.path, method)
        for route in leaf_routes(app.routes)
        if getattr(route, "path", "").startswith("/api/v1")
        for method in getattr(route, "methods", set())
    ]
    assert registered
    assert len(registered) == len(set(registered))


def test_inventory_only_query_routes_to_inventory_bee() -> None:
    payload = {"question": "How many Product A units are left?", "language": "en", "user": "owner"}
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["inventory"]
    assert body["guard_decision"] == "approval_required"
    assert body["approval_required"] is True


def test_cross_functional_query_returns_specialist_contract() -> None:
    payload = {"question": "Why did sales fall this week?", "language": "en", "user": "owner"}
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["sales", "inventory"]
    assert "advisor_result" in body
    assert body["advisor_result"]["agent"] == "advisor"
    advisor_evidence = {item["metric"]: item["value"] for item in body["advisor_result"]["evidence"]}
    assert advisor_evidence["relationship_assessment"] == "strongly_supported"

    specialist = body["specialist_results"][0]
    assert set(specialist).issuperset(
        {"agent", "status", "summary", "evidence", "confidence", "recommended_actions"}
    )


def test_sales_inventory_query_correlates_stockout_with_revenue_decline() -> None:
    payload = {
        "question": "Why did sales revenue decline this week and is it linked to stock shortages?",
        "language": "en",
        "user": "owner",
    }
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["sales", "inventory"]
    advisor_evidence = {item["metric"]: item["value"] for item in body["advisor_result"]["evidence"]}
    assert advisor_evidence["linked_product_id"] == "PRD001"
    assert advisor_evidence["stockout_explained_decline_pct"] == 100.0
    assert advisor_evidence["relationship_assessment"] == "strongly_supported"
    assert advisor_evidence["period_aligned"] is True
    assert advisor_evidence["timeline_aligned"] is True
    assert body["guard_decision"] == "approval_required"
    assert body["approval_required"] is True


def test_query_persists_retrievable_audit_event() -> None:
    payload = {"question": "Why did sales fall this week?", "language": "en", "user": "owner"}
    query_response = client.post("/api/v1/query", json=payload)
    workflow_id = query_response.json()["workflow_id"]

    audit_response = client.get(f"/api/v1/audit/{workflow_id}")

    assert audit_response.status_code == 200
    event = audit_response.json()
    assert event["workflow_id"] == workflow_id
    assert event["question"] == payload["question"]
    assert event["user"] == "owner"
    assert event["decision"] == query_response.json()["guard_decision"]
    assert event["created_at"]
    assert event["actions"]


def test_chinese_query_routes_and_returns_chinese_summary() -> None:
    payload = {
        "question": "为什么本周销售收入下降，是否和库存缺货有关？",
        "language": "zh-CN",
        "user": "owner",
    }
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["sales", "inventory"]
    assert "下降" in body["specialist_results"][0]["summary"]
    assert "销售和库存证据" in body["advisor_result"]["summary"]
