from backend.advisor.advisor import advisor_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RiskLevel


def specialist(
    agent: str,
    summary: str,
    evidence: list[tuple[str, object]],
    *,
    status: AgentStatus = AgentStatus.SUCCESS,
) -> AgentResponse:
    return AgentResponse(
        agent=agent,
        status=status,
        summary=summary,
        evidence=[Evidence(metric=metric, value=value) for metric, value in evidence],
        confidence=0.8,
    )


def action_types(result: AgentResponse) -> list[str]:
    return [action.type for action in result.recommended_actions]


def test_sales_decline_with_stock_shortage_cites_both_sources() -> None:
    result = advisor_bee(
        "Why are sales down?",
        [
            specialist("sales", "Sales trend indicates a week-on-week decline.", [("latest_revenue", 1500)]),
            specialist("inventory", "Inventory is below threshold.", [("current_stock", 14), ("reorder_level", 20)]),
        ],
    )

    assert result.status == AgentStatus.SUCCESS
    assert any("review_sales_decline" in item for item in action_types(result))
    assert any("review_inventory_shortage" in item for item in action_types(result))
    assert "sales.latest_revenue" in " ".join(action_types(result))
    assert "inventory.current_stock" in " ".join(action_types(result))
    assert "does not establish causation" in result.summary
    assert all(action.risk_level == RiskLevel.GREEN for action in result.recommended_actions)


def test_sales_decline_with_customer_complaints_and_pending_enquiries() -> None:
    result = advisor_bee(
        "Why are sales down?",
        [
            specialist("sales", "Sales fell this week.", [("latest_revenue", 900)]),
            specialist(
                "customer",
                "Customer complaints and unanswered enquiries were reported.",
                [("complaint_rate_pct", 4.2), ("unanswered_leads", 3)],
            ),
        ],
    )

    types = action_types(result)
    assert any("review_customer_complaints" in item for item in types)
    assert any("review_pending_enquiries" in item for item in types)
    assert "may be related" in result.summary
    assert "does not establish causation" in result.summary


def test_financial_concern_requires_supporting_evidence() -> None:
    result = advisor_bee(
        "How is cash flow?",
        [
            specialist(
                "finance",
                "Overdue invoices are affecting cash flow.",
                [("overdue_invoice_count", 2), ("overdue_amount_sgd", 4200)],
            )
        ],
    )

    assert len(result.recommended_actions) == 1
    assert "review_financial_exposure" in result.recommended_actions[0].type
    assert "finance.overdue_amount_sgd" in result.recommended_actions[0].type


def test_missing_specialist_results_returns_partial_without_recommendations() -> None:
    result = advisor_bee("Summarize the business", [])

    assert result.status == AgentStatus.PARTIAL
    assert result.confidence == 0.0
    assert result.recommended_actions == []
    assert "No usable specialist results" in result.summary


def test_conflicting_sales_evidence_withholds_recommendation() -> None:
    result = advisor_bee(
        "How are sales trending?",
        [
            specialist(
                "sales",
                "Sales trend indicates a week-on-week decline.",
                [("revenue_change_pct", -8), ("revenue_change_pct", 5)],
            )
        ],
    )

    assert result.status == AgentStatus.PARTIAL
    assert result.recommended_actions == []
    assert "Sales direction is conflicting" in result.summary


def test_no_significant_problems_produces_no_recommendations() -> None:
    result = advisor_bee(
        "Any problems?",
        [
            specialist("inventory", "Inventory level is healthy.", [("current_stock", 30), ("reorder_level", 20)]),
            specialist("finance", "No overdue invoices were found.", [("overdue_invoice_count", 0), ("overdue_amount_sgd", 0)]),
        ],
    )

    assert result.status == AgentStatus.SUCCESS
    assert result.recommended_actions == []
    assert "No significant problems" in result.summary


def test_partial_specialist_is_used_but_advisor_marks_result_partial() -> None:
    result = advisor_bee(
        "Review sales",
        [specialist("sales", "Sales declined.", [("latest_revenue", 100)], status=AgentStatus.PARTIAL)],
    )

    assert result.status == AgentStatus.PARTIAL
    assert len(result.recommended_actions) == 1
    assert "sales.latest_revenue" in result.recommended_actions[0].type


def test_summary_without_relevant_evidence_does_not_create_recommendation() -> None:
    result = advisor_bee(
        "How is cash flow?",
        [specialist("finance", "Overdue invoices are affecting cash flow.", [("customer_count", 12)])],
    )

    assert result.recommended_actions == []


def test_failed_specialist_evidence_is_not_treated_as_verified() -> None:
    result = advisor_bee(
        "How are sales?",
        [specialist("sales", "Sales declined.", [("revenue_change_pct", -12)], status=AgentStatus.FAILED)],
    )

    assert result.status == AgentStatus.PARTIAL
    assert result.evidence == []
    assert result.recommended_actions == []