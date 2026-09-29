from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class RiskLevel(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class Evidence(BaseModel):
    metric: str
    value: Any
    unit: str | None = None
    period: str | None = None
    source: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class RecommendedAction(BaseModel):
    type: str
    risk_level: RiskLevel = RiskLevel.GREEN
    reason: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_impact: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent: str
    status: AgentStatus
    summary: str
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="en", min_length=2, max_length=16)
    user: str = Field(default="owner")


class QueryResponse(BaseModel):
    workflow_id: str
    invoked_agents: list[str]
    specialist_results: list[AgentResponse]
    advisor_result: AgentResponse
    guard_decision: str
    approval_required: bool
