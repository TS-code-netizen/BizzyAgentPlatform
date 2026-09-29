from __future__ import annotations

import pytest

from backend.advisor.advisor import advisor_bee
from backend.agents.inventory import inventory_bee
from backend.agents.sales import sales_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence
from backend.orchestration.queen import run_specialists


def evidence_map(response: AgentResponse) -> dict[str, object]:
    return {item.metric: item.value for item in response.evidence}


@pytest.mark.parametrize(
    ("question", "expected_metric"),
    [
        ("What was our total sales revenue and unit volume for the past week?", "recent_revenue_sgd"),
        ("Why did our weekly sales revenue drop compared to the baseline period?", "volume_effect_sgd"),
        ("Which sales channels generated the most revenue?", "channel_performance_details"),
        ("Can you give me a summary of our top 5 revenue-generating products?", "top_product_details"),
        ("How does our current gross margin compare across product categories?", "category_margin_details"),
    ],
)
def test_sales_bee_answers_benchmark_intents(question: str, expected_metric: str, fixture_data_dir) -> None:
    response = sales_bee(question=question, data_dir=fixture_data_dir)

    assert response.status.value in {"success", "partial"}
    assert expected_metric in evidence_map(response)
    assert response.summary


@pytest.mark.parametrize(
    ("question", "expected_metric"),
    [
        (
            "Are there products currently out of stock or below their reorder threshold?",
            "at_or_below_reorder_products",
        ),
        ("What is the total FIFO stock valuation right now?", "total_stock_value_sgd"),
        ("How many unfulfilled units occurred for Product A (PRD001)?", "recent_unfulfilled_demand_units"),
        ("Which suppliers have the longest lead times?", "supplier_lead_time_details"),
        ("Do we have enough inventory for our top 10 best-selling items?", "top_seller_stock_details"),
    ],
)
def test_inventory_bee_answers_benchmark_intents(
    question: str,
    expected_metric: str,
    fixture_data_dir,
) -> None:
    response = inventory_bee(question=question, data_dir=fixture_data_dir)

    assert response.status.value in {"success", "partial"}
    assert expected_metric in evidence_map(response)
    assert response.summary


@pytest.mark.parametrize(
    ("question", "expected_metric"),
    [
        (
            "Why did our sales revenue decline this week and is it linked to stock shortages?",
            "relationship_assessment",
        ),
        (
            "Which of our top best-selling products are at risk of running out of stock soon?",
            "top_sellers_at_stock_risk",
        ),
        (
            "How many sales were lost because Product A (PRD001) was out of stock?",
            "stockout_explained_decline_pct",
        ),
        (
            "Which products have high inventory valuation but low sales velocity?",
            "high_value_low_velocity_products",
        ),
        (
            "Do we need to place new purchase orders to support our current sales revenue targets?",
            "replenishment_priorities",
        ),
    ],
)
def test_advisor_synthesizes_sales_inventory_benchmark(question: str, expected_metric: str) -> None:
    selected, specialists = run_specialists(question)
    response = advisor_bee(question, specialists)

    assert selected == ["sales", "inventory"]
    assert expected_metric in evidence_map(response)
    assert not response.summary.startswith("Advisor analysis for")


def test_advisor_prioritises_purchase_order_intent_over_generic_decline_link() -> None:
    question = "Revenue declined; should we place purchase orders to support our sales target?"
    _, specialists = run_specialists(question)

    response = advisor_bee(question, specialists)

    assert "replenishment_priorities" in evidence_map(response)
    assert "relationship_assessment" not in evidence_map(response)


def test_advisor_keeps_customer_and_finance_findings_with_stockout_link(fixture_data_dir) -> None:
    question = "Why did revenue decline, considering complaints, overdue invoices, and stockouts?"
    sales = sales_bee(question=question, data_dir=fixture_data_dir)
    inventory = inventory_bee(question=question, data_dir=fixture_data_dir)
    customer = AgentResponse(
        agent="customer",
        status=AgentStatus.SUCCESS,
        summary="Customer complaints increased.",
        evidence=[Evidence(metric="customer_test_metric", value=1)],
        confidence=0.8,
    )
    finance = AgentResponse(
        agent="finance",
        status=AgentStatus.SUCCESS,
        summary="Overdue invoices increased.",
        evidence=[Evidence(metric="finance_test_metric", value=2)],
        confidence=0.7,
    )

    response = advisor_bee(question, [sales, customer, finance, inventory])
    evidence = evidence_map(response)

    assert evidence["relationship_assessment"] == "strongly_supported"
    assert evidence["customer_test_metric"] == 1
    assert evidence["finance_test_metric"] == 2
    assert "[CUSTOMER]" in response.summary
    assert "[FINANCE]" in response.summary
    assert response.confidence == 0.7


def test_top_seller_risk_includes_baseline_bestseller_that_is_now_stocked_out() -> None:
    question = "Which top best-selling products are at risk of running out of stock?"
    _, specialists = run_specialists(question)

    response = advisor_bee(question, specialists)
    product_ids = {
        row["product_id"] for row in evidence_map(response)["top_sellers_at_stock_risk"]
    }

    assert "PRD001" in product_ids

