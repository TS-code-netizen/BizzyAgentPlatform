from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.agents.sales import sales_bee
from backend.models.agent import AgentResponse, AgentStatus, RiskLevel
from backend.tools.sales_tools import Window, comparison_windows, summarise_sales

AS_OF = date(2026, 9, 23)
SALES_HEADER = "date,product_id,product,quantity,revenue,cost_of_goods_sold,channel"


def evidence_map(response: AgentResponse) -> dict[str, object]:
    return {item.metric: item.value for item in response.evidence}


def test_comparison_windows_are_adjacent_and_inclusive() -> None:
    baseline, recent = comparison_windows(AS_OF, 7)

    assert recent == Window(date(2026, 9, 17), date(2026, 9, 23))
    assert baseline == Window(date(2026, 9, 10), date(2026, 9, 16))


def test_comparison_windows_reject_empty_window() -> None:
    with pytest.raises(ValueError):
        comparison_windows(AS_OF, 0)


def test_summarise_sales_ignores_rows_outside_windows(fixture_data_dir) -> None:
    summary = summarise_sales(fixture_data_dir, AS_OF)

    # The fixture also has sales on 2026-09-09 and 2026-09-24, which must not be counted.
    assert summary.baseline_revenue == Decimal("8400.00")
    assert summary.recent_revenue == Decimal("6300.00")
    assert summary.revenue_change_pct == -25.0
    assert (summary.baseline_units, summary.recent_units) == (126, 105)
    assert summary.recent_gross_margin_pct == 45.56
    assert summary.coverage == 1.0


def test_summarise_sales_breaks_down_channels_products_and_categories(fixture_data_dir) -> None:
    summary = summarise_sales(fixture_data_dir, AS_OF)

    assert {channel.channel: channel.recent_revenue for channel in summary.channels} == {
        "marketplace": Decimal("3500.00"),
        "store": Decimal("2800.00"),
        "web": Decimal("0.00"),
    }
    assert [product.product_id for product in summary.top_products(5)] == ["PRD003", "PRD002"]
    assert {category.category: category.margin_pct for category in summary.categories} == {
        "Kitchen": 40.0,
        "Outdoor": 50.0,
    }


def test_decline_is_attributed_to_product_that_stopped_selling(fixture_data_dir) -> None:
    summary = summarise_sales(fixture_data_dir, AS_OF)
    top = summary.top_decliner

    assert top is not None
    assert top.product_id == "PRD001"
    assert top.revenue_change == Decimal("-2100.00")
    assert summary.share_of_decline_pct(top) == 100.0
    assert top.last_sale_date == date(2026, 9, 16)
    assert [product.product_id for product in summary.stopped_selling] == ["PRD001"]


def test_sales_bee_returns_contract_with_evidence(fixture_data_dir) -> None:
    response = sales_bee(as_of=AS_OF, data_dir=fixture_data_dir)
    evidence = evidence_map(response)

    AgentResponse.model_validate(response.model_dump())
    assert response.agent == "sales"
    assert response.status is AgentStatus.SUCCESS
    assert response.confidence == 0.95
    assert evidence["baseline_revenue_sgd"] == 8400.0
    assert evidence["recent_revenue_sgd"] == 6300.0
    assert evidence["revenue_change_pct"] == -25.0
    assert evidence["recent_units"] == 105
    assert evidence["top_channel"] == "marketplace"
    assert evidence["recent_revenue_by_channel_sgd"] == "marketplace: 3,500.00 | store: 2,800.00 | web: 0.00"
    assert evidence["top_products_recent_revenue_sgd"] == (
        "PRD003 Insulated Bottle Model 03: 3,500.00 | PRD002 Storage Box Model 02: 2,800.00"
    )
    assert evidence["recent_gross_margin_pct_by_category"] == "Outdoor: 50.00% | Kitchen: 40.00%"
    assert evidence["focus_product_id"] == "PRD001"
    assert evidence["products_with_no_recent_sales"] == "PRD001"
    assert evidence["top_product_details"][0] == {
        "product_id": "PRD003",
        "product": "Insulated Bottle Model 03",
        "recent_revenue_sgd": 3500.0,
        "recent_units": 70,
    }
    assert evidence["channel_performance_details"][0]["channel"] == "marketplace"
    assert evidence["category_margin_details"][0]["category"] == "Outdoor"
    assert [(action.type, action.risk_level) for action in response.recommended_actions] == [
        ("investigate_stock_availability", RiskLevel.GREEN)
    ]
    assert "25.0%" in response.summary
    assert "no sales since 2026-09-16" in response.summary


def test_sales_bee_selects_channel_analysis_for_question(fixture_data_dir) -> None:
    response = sales_bee(
        question="Which sales channel generated the most revenue?",
        as_of=AS_OF,
        data_dir=fixture_data_dir,
    )
    evidence = evidence_map(response)

    assert evidence["top_channel"] == "marketplace"
    assert evidence["top_channel_recent_revenue_sgd"] == 3500.0
    assert "focus_product_id" not in evidence
    assert "top_products_recent_revenue_sgd" not in evidence
    assert response.recommended_actions[0].parameters["analysis_intent"] == "channel_performance"


def test_sales_decline_question_includes_volume_price_decomposition(fixture_data_dir) -> None:
    response = sales_bee(
        question="Why did weekly sales revenue decline?",
        as_of=AS_OF,
        data_dir=fixture_data_dir,
    )
    evidence = evidence_map(response)

    assert evidence["volume_effect_sgd"] == -2100.0
    assert evidence["price_mix_effect_sgd"] == 0.0
    assert response.recommended_actions[0].parameters == {"product_id": "PRD001"}
    assert response.recommended_actions[0].expected_impact == {"revenue_gap_sgd": 2100.0}


def test_sales_bee_reports_growth_without_focus_product(write_csv) -> None:
    data_dir = write_csv(
        "sales.csv",
        SALES_HEADER,
        "2026-09-16,PRD003,Insulated Bottle Model 03,10,500.00,300.00,store",
        "2026-09-23,PRD003,Insulated Bottle Model 03,12,600.00,360.00,store",
    )

    response = sales_bee(as_of=AS_OF, data_dir=data_dir)
    evidence = evidence_map(response)

    assert response.status is AgentStatus.SUCCESS
    assert evidence["revenue_change_pct"] == 20.0
    assert "focus_product_id" not in evidence
    assert "recent_gross_margin_pct_by_category" not in evidence
    assert response.recommended_actions[0].type == "monitor_sales_trend"
    assert response.confidence == 0.65


def test_sales_bee_without_baseline_is_partial(write_csv) -> None:
    data_dir = write_csv("sales.csv", SALES_HEADER, "2026-09-20,PRD002,Storage Box Model 02,5,400.00,240.00,web")

    response = sales_bee(as_of=AS_OF, data_dir=data_dir)
    evidence = evidence_map(response)

    assert response.status is AgentStatus.PARTIAL
    assert "revenue_change_pct" not in evidence
    assert evidence["recent_revenue_sgd"] == 400.0


def test_sales_bee_fails_gracefully_when_data_missing(tmp_path) -> None:
    response = sales_bee(as_of=AS_OF, data_dir=tmp_path)

    assert response.status is AgentStatus.FAILED
    assert response.confidence == 0.0
    assert response.evidence == []
    assert response.recommended_actions == []


def test_sales_bee_fails_gracefully_on_unexpected_schema(write_csv) -> None:
    data_dir = write_csv("sales.csv", "date,product,quantity,revenue", "2026-09-22,Product A,30,1500")

    response = sales_bee(as_of=AS_OF, data_dir=data_dir)

    assert response.status is AgentStatus.FAILED
