from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import csv
from collections import defaultdict

import duckdb

from backend.tools.sales_tools import sql_path

INVOICE_COLUMN_TYPES = (
    "{'invoice_id': 'VARCHAR', 'due_date': 'DATE', 'amount': 'DECIMAL(14,2)', "
    "'paid_amount': 'DECIMAL(14,2)', 'outstanding_amount': 'DECIMAL(14,2)', "
    "'currency': 'VARCHAR', 'status': 'VARCHAR'}"
)


@dataclass(frozen=True)
class ReceivablesSummary:
    as_of: date
    overdue_invoice_count: int
    overdue_outstanding: Decimal
    ageing: dict[str, Decimal] | None = None
    customer_exposure: dict[str, Decimal] | None = None


def assess_receivables(data_dir: Path, as_of: date) -> ReceivablesSummary:
    invoices_path = data_dir / "invoices.csv"
    if not invoices_path.exists():
        raise FileNotFoundError(f"invoices.csv not found in {data_dir}")

    if (data_dir / "payments.csv").exists():
        return _dated_receivables(data_dir, as_of)
    with invoices_path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row.get("as_of_date") and date.fromisoformat(row["as_of_date"]) != as_of:
                raise ValueError("Historical receivables require dated payments, not current invoice balances.")
            if row.get("currency") != "SGD":
                raise ValueError("Finance reports require SGD; currency conversion is not implemented.")

    con = duckdb.connect()
    try:
        count, outstanding = con.execute(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE outstanding_amount > 0
                      AND due_date < $as_of
                ),
                COALESCE(
                    SUM(outstanding_amount) FILTER (
                        WHERE outstanding_amount > 0
                          AND due_date < $as_of
                    ),
                    0
                )
            FROM read_csv(
                {sql_path(invoices_path)},
                header = true,
                types = {INVOICE_COLUMN_TYPES}
            )
            """,
            {"as_of": as_of},
        ).fetchone()
    finally:
        con.close()

    return ReceivablesSummary(
        as_of=as_of,
        overdue_invoice_count=int(count),
        overdue_outstanding=Decimal(outstanding),
    )


def _money(value: str) -> Decimal:
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Expected a finite non-negative amount with at most two decimal places.")
    return amount


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row.get("currency") != "SGD":
                raise ValueError("Mixed or unsupported currency in finance data.")
            yield row


def _dated_receivables(data_dir: Path, as_of: date) -> ReceivablesSummary:
    invoices = {}
    for row in _rows(data_dir / "invoices.csv"):
        if row["invoice_id"] in invoices:
            raise ValueError("Duplicate invoice ID.")
        invoices[row["invoice_id"]] = row
    paid = defaultdict(Decimal)
    payment_ids = set()
    for row in _rows(data_dir / "payments.csv"):
        if row["payment_id"] in payment_ids or row["invoice_id"] not in invoices:
            raise ValueError("Duplicate payment or unknown invoice reference.")
        payment_ids.add(row["payment_id"])
        invoice = invoices[row["invoice_id"]]
        payment_date = date.fromisoformat(row["payment_date"])
        if row["customer_id"] != invoice["customer_id"] or payment_date < date.fromisoformat(invoice["issue_date"]):
            raise ValueError("Payment does not match its invoice customer/date.")
        amount = _money(row["amount"])
        if payment_date <= as_of:
            paid[row["invoice_id"]] += amount
    ageing = dict.fromkeys(["not_due", "1_30", "31_60", "61_90", "over_90"], Decimal(0))
    exposure = defaultdict(Decimal)
    count = 0
    for invoice_id, row in invoices.items():
        if date.fromisoformat(row["issue_date"]) > as_of:
            continue
        outstanding = _money(row["amount"]) - paid[invoice_id]
        if outstanding < 0:
            raise ValueError("Payments exceed invoice amount.")
        if not outstanding:
            continue
        overdue_days = (as_of - date.fromisoformat(row["due_date"])).days
        bucket = "not_due" if overdue_days <= 0 else "1_30" if overdue_days <= 30 else "31_60" if overdue_days <= 60 else "61_90" if overdue_days <= 90 else "over_90"
        ageing[bucket] += outstanding
        exposure[row["customer_id"]] += outstanding
        count += overdue_days > 0
    return ReceivablesSummary(as_of, count, sum((amount for bucket, amount in ageing.items() if bucket != "not_due"), Decimal(0)), ageing, dict(sorted(exposure.items(), key=lambda item: (-item[1], item[0]))))


@dataclass(frozen=True)
class FinancePeriod:
    start: date
    end: date
    metrics: dict[str, Decimal]
    expenses: dict[str, Decimal]
    cash_movements: dict[str, Decimal]


def assess_financial_period(data_dir: Path, start: date, end: date) -> FinancePeriod:
    if not date(2023, 1, 1) <= start <= end <= date(2026, 9, 23):
        raise ValueError("Period must fall within the verified dataset coverage 2023-01-01 through 2026-09-23.")
    accounts = {}
    for row in _rows(data_dir / "accounts.csv"):
        if row["account_code"] in accounts:
            raise ValueError("Duplicate account code.")
        accounts[row["account_code"]] = row["account_type"]
    if accounts.get("1000") != "asset":
        raise ValueError("Expected the dataset Cash account 1000.")
    duration = (end - start).days + 1
    previous_start, previous_end = start - timedelta(days=duration), start - timedelta(days=1)
    current = defaultdict(Decimal)
    previous = defaultdict(Decimal)
    expenses = defaultdict(Decimal)
    cash_movements = defaultdict(Decimal)
    journals = defaultdict(Decimal)
    journal_dates = {}
    keys = set()
    opening_cash = closing_cash = cash_in = cash_out = Decimal(0)
    for row in _rows(data_dir / "accounting_ledger.csv"):
        posting = date.fromisoformat(row["posting_date"])
        account = row["account_code"]
        key = (row["journal_id"], row["line_number"])
        if key in keys or account not in accounts:
            raise ValueError("Duplicate ledger line or unknown account.")
        keys.add(key)
        debit, credit = _money(row["debit"]), _money(row["credit"])
        if (debit > 0) == (credit > 0):
            raise ValueError("A journal line must have exactly one positive debit or credit.")
        balance = debit - credit
        journal = row["journal_id"]
        if journal in journal_dates and journal_dates[journal] != posting:
            raise ValueError("Journal lines have inconsistent dates.")
        journal_dates[journal] = posting
        journals[journal] += balance
        opening = row["source_file"] in {"opening_balances", "opening_balances.csv"}
        if account == "1000" and posting <= end:
            closing_cash += balance
            if posting < start or opening:
                opening_cash += balance
            elif start <= posting:
                cash_in += debit
                cash_out += credit
                cash_movements[row["source_file"]] += balance
        if opening:
            continue
        if start <= posting <= end:
            current[accounts[account]] += balance
            if accounts[account] == "operating_expense":
                expenses[account] += balance
        elif previous_start <= posting <= previous_end:
            previous[accounts[account]] += balance
    if not journals:
        raise ValueError("Accounting ledger is empty.")
    if any(journals.values()):
        raise ValueError("Unbalanced accounting journal; refusing financial totals.")
    net_revenue = -current["income"] - current["contra_income"]
    gross_profit = net_revenue - current["cost_of_sales"]
    profit = gross_profit - current["operating_expense"]
    metrics = {
        "net_revenue_sgd": net_revenue,
        "cost_of_goods_sold_sgd": current["cost_of_sales"],
        "gross_profit_sgd": gross_profit,
        "operating_expenses_sgd": current["operating_expense"],
        "net_profit_before_tax_sgd": profit,
        "opening_cash_sgd": opening_cash, "cash_receipts_sgd": cash_in,
        "cash_payments_sgd": cash_out, "net_cash_flow_sgd": cash_in - cash_out,
        "closing_cash_sgd": closing_cash,
    }
    if previous_start >= date(2023, 1, 1):
        prior_revenue = -previous["income"] - previous["contra_income"]
        prior_profit = prior_revenue - previous["cost_of_sales"] - previous["operating_expense"]
        metrics.update(previous_net_revenue_sgd=prior_revenue, previous_net_profit_before_tax_sgd=prior_profit,
                       net_revenue_change_sgd=net_revenue-prior_revenue, net_profit_change_sgd=profit-prior_profit)
    if opening_cash + cash_in - cash_out != closing_cash:
        raise ValueError("Cash bridge does not reconcile.")
    return FinancePeriod(start, end, metrics, dict(sorted(expenses.items())), dict(sorted(cash_movements.items())))
