"""Regression checks against the frozen flagship numbers in BizzyData's scenario_expectations.csv."""

from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tools.inventory_tools import assess_inventory
from backend.tools.finance_tools import assess_receivables
from backend.tools.sales_tools import summarise_sales

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DATA_DIR = Path(os.getenv("BIZZY_SCENARIO_DATA_DIR", str(ROOT.parent / "BizzyData" / "data" / "demo")))
AS_OF = date(2026, 9, 23)

pytestmark = pytest.mark.skipif(
    not (SCENARIO_DATA_DIR / "scenario_expectations.csv").exists(),
    reason="BizzyData checkout not found; set BIZZY_SCENARIO_DATA_DIR to its data/demo folder",
)


@pytest.fixture(scope="module")
def expected() -> dict[str, dict[str, str]]:
    with (SCENARIO_DATA_DIR / "scenario_expectations.csv").open(encoding="utf-8") as handle:
        return {row["metric"]: row for row in csv.DictReader(handle)}


def test_sales_decline_matches_frozen_scenario(expected) -> None:
    summary = summarise_sales(SCENARIO_DATA_DIR, AS_OF)

    assert summary.baseline.start.isoformat() == expected["baseline_revenue"]["period_start"]
    assert summary.recent.end.isoformat() == expected["recent_revenue"]["period_end"]
    assert summary.baseline_revenue == Decimal(expected["baseline_revenue"]["expected_value"])
    assert summary.recent_revenue == Decimal(expected["recent_revenue"]["expected_value"])
    assert summary.revenue_change_pct == float(expected["revenue_change_pct"]["expected_value"])
    assert summary.top_decliner is not None
    assert summary.top_decliner.product_id == "PRD001"
    assert summary.share_of_decline_pct(summary.top_decliner) == 100.0


def test_product_a_shortage_matches_frozen_scenario(expected) -> None:
    status = assess_inventory(SCENARIO_DATA_DIR, AS_OF)

    assert status.focus is not None
    assert status.focus.product_id == "PRD001"
    assert status.focus.current_stock == int(expected["product_a_current_stock"]["expected_value"])
    assert status.focus.recent_unfulfilled_units == int(expected["product_a_unfulfilled_demand"]["expected_value"])
    assert [item.product_id for item in status.out_of_stock] == ["PRD001"]


def test_lost_stock_sales_explain_the_revenue_decline() -> None:
    summary = summarise_sales(SCENARIO_DATA_DIR, AS_OF)
    status = assess_inventory(SCENARIO_DATA_DIR, AS_OF)

    assert summary.top_decliner is not None and status.focus is not None
    assert status.focus.product_id == summary.top_decliner.product_id
    assert status.focus.recent_lost_revenue == -summary.top_decliner.revenue_change


def test_overdue_receivables_match_frozen_scenario(expected) -> None:
    summary = assess_receivables(SCENARIO_DATA_DIR, AS_OF)

    assert summary.overdue_invoice_count == int(expected["overdue_invoice_count"]["expected_value"])
    assert summary.overdue_outstanding == Decimal(expected["overdue_outstanding"]["expected_value"])
