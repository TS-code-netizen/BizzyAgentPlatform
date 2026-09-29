from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.agents.finance import finance_bee
from backend.models.agent import AgentStatus
from backend.tools.finance_tools import assess_receivables

AS_OF = date(2026, 9, 23)


def evidence_map(response) -> dict[str, object]:
    return {item.metric: item.value for item in response.evidence}


def test_receivables_use_outstanding_balance_and_due_date(fixture_data_dir) -> None:
    summary = assess_receivables(fixture_data_dir, AS_OF)

    assert summary.overdue_invoice_count == 2
    assert summary.overdue_outstanding == Decimal("280.00")


def test_finance_bee_returns_dynamic_overdue_summary(fixture_data_dir) -> None:
    response = finance_bee(as_of=AS_OF, data_dir=fixture_data_dir)
    evidence = evidence_map(response)

    assert response.status is AgentStatus.SUCCESS
    assert evidence["overdue_invoice_count"] == 2
    assert evidence["overdue_outstanding_sgd"] == 280.0
    assert "2 invoices" in response.summary
    assert response.recommended_actions[0].parameters["overdue_invoice_count"] == 2


def test_finance_bee_fails_when_invoice_data_is_missing(tmp_path) -> None:
    response = finance_bee(as_of=AS_OF, data_dir=tmp_path)

    assert response.status is AgentStatus.FAILED
    assert response.confidence == 0.0

