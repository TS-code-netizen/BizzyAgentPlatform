from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import uuid4

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.advisor.advisor import advisor_bee
from backend.agents.finance import finance_bee
from backend.api.finance_reports import router as finance_reports_router
from backend.agents.inventory import inventory_bee
from backend.agents.sales import sales_bee
from backend.audit.store import build_audit_event, get_audit_event, save_audit_event, decide_action, DecisionConflict
from backend.security.auth import Identity, current_identity, require_approver
from backend.models.agent import AgentResponse, QueryRequest, QueryResponse
from backend.models.health import BusinessAlert, SalesInventoryHealth
from backend.orchestration.localization import localize_response
from backend.orchestration.queen import run_specialists
from backend.security.guard import evaluate
from backend.tools import demo_data
from backend.tools.health_tools import build_sales_inventory_health
from dotenv import load_dotenv

load_dotenv()  # Loads environment variables from .env file
router = APIRouter(prefix="/api/v1", tags=["bizzybee"], dependencies=[Depends(current_identity)])
router.include_router(finance_reports_router)


def _sales_inventory_health_or_503(as_of: date, window_days: int) -> SalesInventoryHealth:
    try:
        return build_sales_inventory_health(demo_data.DATA_DIR, as_of, window_days)
    except (FileNotFoundError, duckdb.Error, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Sales or inventory data is unavailable or invalid.",
        ) from exc


@router.get("/business-health")
def business_health() -> dict[str, object]:
    health = _sales_inventory_health_or_503(demo_data.as_of_date(), 7)
    return {
        "score": health.score,
        "status": health.status,
        "as_of": health.as_of.isoformat(),
        "priority_issues": [alert.alert_type for alert in health.priority_issues],
    }


@router.get("/sales/summary", response_model=AgentResponse)
def sales_summary(
    question: Optional[str] = Query(default=None, min_length=1),
    language: str = Query(default="en", min_length=2, max_length=16),
    window_days: int = Query(default=7, ge=1, le=90),
    as_of: Optional[date] = None,
) -> AgentResponse:
    return localize_response(
        sales_bee(question=question, as_of=as_of, window_days=window_days),
        language,
    )


@router.get("/inventory/status", response_model=AgentResponse)
def inventory_status(
    question: Optional[str] = Query(default=None, min_length=1),
    language: str = Query(default="en", min_length=2, max_length=16),
    window_days: int = Query(default=7, ge=1, le=90),
    as_of: Optional[date] = None,
) -> AgentResponse:
    return localize_response(
        inventory_bee(question=question, as_of=as_of, window_days=window_days),
        language,
    )


@router.get("/finance/summary", response_model=AgentResponse)
def finance_summary(
    language: str = Query(default="en", min_length=2, max_length=16),
    as_of: Optional[date] = None,
) -> AgentResponse:
    return localize_response(finance_bee(as_of=as_of), language)


@router.get("/sales-inventory/health", response_model=SalesInventoryHealth)
def sales_inventory_health(
    window_days: int = Query(default=7, ge=1, le=90),
    as_of: Optional[date] = None,
) -> SalesInventoryHealth:
    reporting_date = as_of or demo_data.as_of_date()
    return _sales_inventory_health_or_503(reporting_date, window_days)


@router.get("/sales-inventory/alerts", response_model=list[BusinessAlert])
def sales_inventory_alerts(
    window_days: int = Query(default=7, ge=1, le=90),
    as_of: Optional[date] = None,
) -> list[BusinessAlert]:
    reporting_date = as_of or demo_data.as_of_date()
    health = _sales_inventory_health_or_503(reporting_date, window_days)
    return health.priority_issues


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, identity: Identity = Depends(current_identity)) -> QueryResponse:
    workflow_id = str(uuid4())
    invoked_agents, specialist_results = run_specialists(payload.question, payload.language)
    advisor_result = localize_response(
        advisor_bee(payload.question, specialist_results),
        payload.language,
    )

    guard_decision, approval_required = evaluate([*specialist_results, advisor_result])
    audit_event = build_audit_event(
        workflow_id,
        identity.subject,
        [*specialist_results, advisor_result],
        guard_decision,
        question=payload.question,
    )
    save_audit_event(audit_event)

    return QueryResponse(
        workflow_id=workflow_id,
        invoked_agents=invoked_agents,
        specialist_results=specialist_results,
        advisor_result=advisor_result,
        guard_decision=guard_decision,
        approval_required=approval_required,
    )


@router.get("/audit/{workflow_id}")
def audit_event(workflow_id: str, identity: Identity = Depends(current_identity)) -> dict[str, object]:
    event = get_audit_event(workflow_id)
    if event is None or (event["user"] != identity.subject and not identity.approver):
        raise HTTPException(status_code=404, detail="Workflow audit event not found.")
    return event


class DecisionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/me")
def me(identity: Identity = Depends(current_identity)) -> dict:
    return {"subject": identity.subject, "approver": identity.approver}


def _decide(action_id: str, actor: Identity, decision: str, payload: DecisionRequest) -> dict:
    try:
        return decide_action(action_id, actor.subject, decision, payload.reason)
    except KeyError as exc:
        raise HTTPException(404, "Action not found.") from exc
    except DecisionConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/actions/{action_id}/approve")
def approve(action_id: str, payload: DecisionRequest, actor: Identity = Depends(require_approver)) -> dict:
    return _decide(action_id, actor, "approved", payload)


@router.post("/actions/{action_id}/reject")
def reject(action_id: str, payload: DecisionRequest, actor: Identity = Depends(require_approver)) -> dict:
    return _decide(action_id, actor, "rejected", payload)
