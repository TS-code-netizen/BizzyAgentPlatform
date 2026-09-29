from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.finance import finance_bee
from backend.models.agent import AgentStatus, Evidence

ReportType = Literal["profitability", "operating_expenses", "cash_flow", "receivables"]
router = APIRouter()


class FinanceReport(BaseModel):
    report_type: ReportType
    start_date: date | None
    as_of_date: date
    currency: Literal["SGD"] = "SGD"
    summary: str
    evidence: list[Evidence]


@router.get("/finance/report", response_model=FinanceReport)
def finance_report(
    report_type: ReportType,
    start_date: date | None = None,
    as_of_date: date = date(2026, 9, 23),
) -> FinanceReport:
    if not date(2023, 1, 1) <= as_of_date <= date(2026, 9, 23):
        raise HTTPException(422, "Reporting date is outside dataset coverage.")
    if report_type == "receivables" and start_date is not None:
        raise HTTPException(422, "Receivables uses only an as-of date.")
    start = None if report_type == "receivables" else start_date or as_of_date.replace(day=1)
    if start is not None and not date(2023, 1, 1) <= start <= as_of_date:
        raise HTTPException(422, "Invalid reporting period.")
    question = {"profitability": "profit", "operating_expenses": "expenses",
                "cash_flow": "cash", "receivables": "receivables"}[report_type]
    response = finance_bee(question=question, as_of=as_of_date, period_start=start)
    if response.status != AgentStatus.SUCCESS:
        raise HTTPException(503, "Required finance data is unavailable or invalid.")
    return FinanceReport(report_type=report_type, start_date=start, as_of_date=as_of_date,
                         summary=response.summary, evidence=response.evidence)
