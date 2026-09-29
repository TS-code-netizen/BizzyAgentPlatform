import csv
import os
from pathlib import Path
from datetime import date
from decimal import Decimal

import pytest

from backend.agents.finance import finance_bee
from backend.models.agent import AgentStatus
from backend.orchestration.localization import localize_response
from backend.tools.finance_tools import assess_financial_period, assess_receivables


def write_csv(path, rows):
    with path.open("w", newline="") as source:
        writer = csv.DictWriter(source, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def ledger_data(tmp_path):
    types = {"1000": "asset", "1100": "asset", "3000": "equity", "4000": "income", "4100": "contra_income", "5000": "cost_of_sales", "6100": "operating_expense"}
    write_csv(tmp_path / "accounts.csv", [{"account_code": code, "account_type": kind, "currency": "SGD"} for code, kind in types.items()])
    rows = []

    def post(journal, posting, debit_account, credit_account, amount, source):
        for line, account in enumerate([debit_account, credit_account], 1):
            rows.append({"journal_id": journal, "line_number": str(line), "posting_date": posting, "account_code": account,
                         "debit": amount if line == 1 else "0.00", "credit": amount if line == 2 else "0.00", "currency": "SGD", "source_file": source})

    post("opening", "2023-01-01", "1000", "3000", "500.00", "opening_balances.csv")
    post("prior", "2026-08-15", "1000", "4000", "50.00", "sales.csv")
    post("sale", "2026-09-01", "1000", "4000", "200.00", "sales.csv")
    post("cost", "2026-09-01", "5000", "1000", "80.00", "supplier_payments.csv")
    post("return", "2026-09-02", "4100", "1000", "20.00", "returns.csv")
    post("rent", "2026-09-03", "6100", "1000", "30.00", "operating_expenses.csv")
    post("future", "2026-09-24", "1000", "4000", "999.00", "sales.csv")
    write_csv(tmp_path / "accounting_ledger.csv", rows)
    return tmp_path


def test_ledger_profit_cash_and_comparison_are_exact(ledger_data):
    result = assess_financial_period(ledger_data, date(2026, 9, 1), date(2026, 9, 23))
    assert result.metrics["net_revenue_sgd"] == Decimal("180.00")
    assert result.metrics["gross_profit_sgd"] == Decimal("100.00")
    assert result.metrics["net_profit_before_tax_sgd"] == Decimal("70.00")
    assert result.metrics["opening_cash_sgd"] == Decimal("550.00")
    assert result.metrics["closing_cash_sgd"] == Decimal("620.00")
    assert result.metrics["net_cash_flow_sgd"] == Decimal("70.00")
    assert result.metrics["previous_net_revenue_sgd"] == Decimal("50.00")
    assert result.metrics["net_profit_change_sgd"] == Decimal("20.00")
    assert result.expenses == {"6100": Decimal("30.00")}


def test_opening_balance_not_counted_as_income_or_cash_flow(ledger_data):
    result = assess_financial_period(ledger_data, date(2023, 1, 1), date(2026, 9, 23))
    assert result.metrics["opening_cash_sgd"] == Decimal("500.00")
    assert result.metrics["net_cash_flow_sgd"] == Decimal("120.00")
    assert "previous_net_revenue_sgd" not in result.metrics


@pytest.mark.parametrize("mutation", ["unbalanced", "duplicate", "currency", "unknown_account", "nan"])
def test_invalid_ledger_fails_closed(ledger_data, mutation):
    path = ledger_data / "accounting_ledger.csv"
    with path.open() as source:
        rows = list(csv.DictReader(source))
    if mutation == "unbalanced": rows[0]["debit"] = "501.00"
    elif mutation == "duplicate": rows.append(rows[0].copy())
    elif mutation == "currency": rows[0]["currency"] = "USD"
    elif mutation == "unknown_account": rows[0]["account_code"] = "9999"
    else: rows[0]["debit"] = "NaN"
    write_csv(path, rows)
    with pytest.raises(ValueError):
        assess_financial_period(ledger_data, date(2026, 9, 1), date(2026, 9, 23))
    assert finance_bee("profit", data_dir=ledger_data).status is AgentStatus.FAILED


def test_profit_response_and_finance_localization_preserve_intent(ledger_data):
    response = finance_bee("Profit this month", as_of=date(2026, 9, 23), data_dir=ledger_data)
    assert response.status is AgentStatus.SUCCESS
    assert not response.recommended_actions
    assert "SGD 70.00" in response.summary
    translated = localize_response(response, "zh-CN")
    assert translated.summary == response.summary
    assert translated.evidence == response.evidence


def test_last_month_period_is_explicit(ledger_data):
    response = finance_bee("cash flow last month", as_of=date(2026, 9, 23), data_dir=ledger_data)
    evidence = {item.metric: item.value for item in response.evidence}
    assert evidence["period_start"] == "2026-08-01"
    assert evidence["period_end"] == "2026-08-31"
    assert evidence["net_cash_flow_sgd"] == 50.0


def test_missing_ledger_never_falls_back_to_receivables(tmp_path):
    response = finance_bee("operating expenses", data_dir=tmp_path)
    assert response.status is AgentStatus.FAILED
    assert response.evidence == []
    assert "0 张逾期" not in localize_response(response, "zh-CN").summary


@pytest.mark.parametrize("start,end", [(date(2022, 12, 31), date(2023, 1, 1)), (date(2026, 9, 24), date(2026, 9, 24)), (date(2026, 9, 23), date(2026, 9, 1))])
def test_invalid_period_rejected(ledger_data, start, end):
    with pytest.raises(ValueError): assess_financial_period(ledger_data, start, end)


def test_historical_payments_and_ageing_boundaries(tmp_path):
    dues = ["2026-09-23", "2026-09-22", "2026-08-24", "2026-08-23", "2026-07-25", "2026-07-24", "2026-06-25", "2026-06-24"]
    invoices = [{"invoice_id": f"INV{index}", "customer_id": "CUS1", "issue_date": "2026-01-01", "due_date": due, "amount": "100.00", "outstanding_amount": "0.00", "currency": "SGD"} for index, due in enumerate(dues)]
    write_csv(tmp_path / "invoices.csv", invoices)
    write_csv(tmp_path / "payments.csv", [
        {"payment_id": "PAY1", "invoice_id": "INV1", "customer_id": "CUS1", "payment_date": "2026-09-22", "amount": "25.00", "currency": "SGD"},
        {"payment_id": "PAY2", "invoice_id": "INV1", "customer_id": "CUS1", "payment_date": "2026-09-24", "amount": "75.00", "currency": "SGD"},
    ])
    report = assess_receivables(tmp_path, date(2026, 9, 23))
    assert report.overdue_invoice_count == 7
    assert report.overdue_outstanding == Decimal("675.00")
    assert report.ageing == dict(zip(["not_due", "1_30", "31_60", "61_90", "over_90"], map(Decimal, ["100", "175", "200", "200", "100"])))
    assert report.customer_exposure == {"CUS1": Decimal("775.00")}


def test_snapshot_cannot_answer_historical_receivables(tmp_path):
    write_csv(tmp_path / "invoices.csv", [{"invoice_id": "INV1", "as_of_date": "2026-09-23", "currency": "SGD"}])
    with pytest.raises(ValueError): assess_receivables(tmp_path, date(2026, 9, 1))


def test_unsupported_date_phrase_requires_clarification(ledger_data):
    response = finance_bee("Profit in 2024", data_dir=ledger_data)
    assert response.status is AgentStatus.PARTIAL
    assert not response.evidence


def test_zero_revenue_margin_is_undefined(ledger_data):
    response = finance_bee("profit", as_of=date(2026, 7, 23), data_dir=ledger_data)
    evidence = {item.metric: item.value for item in response.evidence}
    assert evidence["gross_margin_pct"] is None
    assert evidence["net_profit_margin_pct"] is None


@pytest.mark.skipif(not os.getenv("BIZZY_FINANCE_DATA_DIR"), reason="Full ledger dataset is not bundled in current runtime")
def test_full_dataset_accounting_scenarios():
    root = Path(os.environ["BIZZY_FINANCE_DATA_DIR"])
    report = assess_financial_period(root, date(2023, 1, 1), date(2026, 9, 23))
    with (root / "scenario_expectations.csv").open() as source:
        expected = {row["metric"]: row["expected_value"] for row in csv.DictReader(source)}
    for metric in ["net_revenue", "gross_profit", "operating_expenses", "net_profit_before_tax", "closing_cash", "net_cash_flow"]:
        assert report.metrics[metric + "_sgd"] == Decimal(expected[metric])
    receivables = assess_receivables(root, date(2026, 9, 23))
    assert receivables.overdue_invoice_count == int(expected["overdue_invoice_count"])
    assert receivables.overdue_outstanding == Decimal(expected["overdue_outstanding"])
