from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.models.agent import RecommendedAction


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class BusinessAlert(BaseModel):
    alert_id: str
    alert_type: str
    severity: AlertSeverity
    agent: str
    title: str
    message: str
    as_of: date
    product_id: str | None = None
    metric: str | None = None
    current_value: Any = None
    threshold: Any = None
    recommended_action: RecommendedAction | None = None


class SalesInventoryHealth(BaseModel):
    score: int = Field(ge=0, le=100)
    status: str
    as_of: date
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    priority_issues: list[BusinessAlert] = Field(default_factory=list)

