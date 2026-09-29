from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from decimal import InvalidOperation
from pathlib import Path

import duckdb

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data
from backend.tools.finance_tools import assess_receivables, assess_financial_period

logger = logging.getLogger(__name__)


def finance_bee(
    question: str | None = None,
    as_of: date | None = None,
    data_dir: Path | None = None,
    period_start: date | None = None,
) -> AgentResponse:
    reporting_date = as_of or demo_data.as_of_date()
    source_dir = data_dir or demo_data.DATA_DIR
    text = (question or "").lower()
    intent = "cash_flow" if any(term in text for term in ("cash", "现金")) else "operating_expenses" if any(term in text for term in ("expense", "rent", "payroll", "utilities", "费用", "支出")) else "profitability" if any(term in text for term in ("profit", "margin", "income", "利润", "盈利")) else "overdue_receivables"
    try:
        if not date(2023, 1, 1) <= reporting_date <= date(2026, 9, 23):
            raise ValueError("Reporting date is outside the verified dataset coverage.")
        if period_start is None and re.search(r"\b(?:20\d{2}|week|quarter|yesterday|today|last year|last \d+|all time)\b", text):
            return AgentResponse(agent="finance", status=AgentStatus.PARTIAL, confidence=0.0,
                                 summary="Specify this month, last month or year to date. Other date ranges require explicit period_start/as_of inputs; no totals were calculated.")
        if intent == "overdue_receivables" and "last month" in text:
            reporting_date = reporting_date.replace(day=1) - timedelta(days=1)
        if intent != "overdue_receivables":
            start = period_start or reporting_date.replace(day=1)
            if period_start is None and "last month" in text:
                reporting_date = start - timedelta(days=1)
                start = reporting_date.replace(day=1)
            elif period_start is None and any(term in text for term in ("year to date", "year-to-date", "ytd")):
                start = reporting_date.replace(month=1, day=1)
            report = assess_financial_period(source_dir, start, reporting_date)
            period = f"{start.isoformat()}/{reporting_date.isoformat()}"
            evidence = [Evidence(metric="analysis_intent", value=intent),
                        Evidence(metric="as_of_date", value=reporting_date.isoformat()),
                        Evidence(metric="period_start", value=start.isoformat()),
                        Evidence(metric="period_end", value=reporting_date.isoformat())]
            previous_period = f"{(start - timedelta(days=(reporting_date - start).days + 1)).isoformat()}/{(start - timedelta(days=1)).isoformat()}"
            evidence.extend(Evidence(metric=metric, value=float(amount), unit="SGD", period=previous_period if metric.startswith("previous_") else period, source="accounting_ledger.csv") for metric, amount in report.metrics.items())
            evidence.extend([
                Evidence(metric="expense_by_account_sgd", value={key: float(value) for key, value in report.expenses.items()}, unit="SGD", period=period, source="accounting_ledger.csv;accounts.csv"),
                Evidence(metric="cash_movement_by_source_sgd", value={key: float(value) for key, value in report.cash_movements.items()}, unit="SGD", period=period, source="accounting_ledger.csv"),
                Evidence(metric="cash_bridge_reconciled", value=True, period=period, source="accounting_ledger.csv"),
                Evidence(metric="comparison_basis", value="preceding equal-length period; omitted when outside dataset coverage"),
            ])
            if "previous_net_revenue_sgd" in report.metrics:
                evidence.extend([
                    Evidence(metric="previous_period_start", value=(start - timedelta(days=(reporting_date - start).days + 1)).isoformat()),
                    Evidence(metric="previous_period_end", value=(start - timedelta(days=1)).isoformat()),
                ])
            metrics = report.metrics
            for metric, numerator in [("gross_margin_pct", metrics["gross_profit_sgd"]), ("net_profit_margin_pct", metrics["net_profit_before_tax_sgd"])]:
                margin = round(numerator * 100 / metrics["net_revenue_sgd"], 2) if metrics["net_revenue_sgd"] > 0 else None
                evidence.append(Evidence(metric=metric, value=float(margin) if margin is not None else None,
                                         unit="percent", period=period, source="accounting_ledger.csv"))
            evidence.append(Evidence(metric="margin_basis", value="net revenue after returns; undefined when net revenue is non-positive"))
            summary_text = (
                f"From {start.isoformat()} through {reporting_date.isoformat()}, net revenue is SGD {metrics['net_revenue_sgd']:,.2f}, "
                f"gross profit SGD {metrics['gross_profit_sgd']:,.2f}, operating expenses SGD {metrics['operating_expenses_sgd']:,.2f}, "
                f"and profit before tax SGD {metrics['net_profit_before_tax_sgd']:,.2f}. "
                f"Cash moved from SGD {metrics['opening_cash_sgd']:,.2f} to SGD {metrics['closing_cash_sgd']:,.2f}; "
                f"net cash flow is SGD {metrics['net_cash_flow_sgd']:,.2f}. Figures are ledger-based, not model arithmetic."
            )
            return AgentResponse(agent="finance", status=AgentStatus.SUCCESS, summary=summary_text, evidence=evidence, confidence=0.95)
        summary = assess_receivables(source_dir, reporting_date)
    except (OSError, duckdb.Error, ValueError, KeyError, InvalidOperation):
        logger.warning("Finance Bee could not validate required finance data in %s", source_dir, exc_info=True)
        return AgentResponse(
            agent="finance",
            status=AgentStatus.FAILED,
            summary="Required finance data is missing or invalid for this reporting period; no financial result was calculated.",
            confidence=0.0,
        )

    outstanding = float(round(summary.overdue_outstanding, 2))
    return AgentResponse(
        agent="finance",
        status=AgentStatus.SUCCESS,
        summary=(
            f"{summary.overdue_invoice_count} invoices are overdue with "
            f"SGD {summary.overdue_outstanding:,.2f} still outstanding as of {summary.as_of.isoformat()}."
        ),
        evidence=[
            Evidence(metric="analysis_intent", value="overdue_receivables"),
            Evidence(metric="as_of_date", value=summary.as_of.isoformat(), source="invoices.csv"),
            Evidence(
                metric="overdue_invoice_count",
                value=summary.overdue_invoice_count,
                unit="invoices",
                source="invoices.csv;payments.csv" if summary.ageing is not None else "invoices.csv",
            ),
            Evidence(
                metric="overdue_outstanding_sgd",
                value=outstanding,
                unit="SGD",
                source="invoices.csv;payments.csv" if summary.ageing is not None else "invoices.csv",
            ),
            *([Evidence(metric="receivables_ageing_sgd", value={key: float(value) for key, value in summary.ageing.items()}, unit="SGD", source="invoices.csv;payments.csv"),
               Evidence(metric="customer_outstanding_sgd", value={key: float(value) for key, value in (summary.customer_exposure or {}).items()}, unit="SGD", source="invoices.csv;payments.csv")]
              if summary.ageing is not None else []),
        ],
        confidence=0.95,
        recommended_actions=[
            RecommendedAction(
                type="prepare_invoice_reminders",
                risk_level=RiskLevel.AMBER,
                reason="Overdue balances require customer follow-up but messages should be approved first.",
                parameters={"overdue_invoice_count": summary.overdue_invoice_count},
                expected_impact={"outstanding_receivables_sgd": outstanding},
            )
        ] if summary.overdue_invoice_count else [],
    )
