from __future__ import annotations

from backend.audit.store import (
    build_audit_event,
    clear_audit_events,
    get_audit_event,
    save_audit_event,
)
from backend.models.agent import AgentResponse, AgentStatus


def test_configured_audit_log_survives_memory_reset(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "audit" / "events.jsonl"
    monkeypatch.setenv("BIZZY_AUDIT_LOG", str(log_path))
    result = AgentResponse(
        agent="sales",
        status=AgentStatus.SUCCESS,
        summary="Sales analysis complete.",
        confidence=1.0,
    )
    event = build_audit_event(
        "workflow-1",
        "owner",
        [result],
        "allowed",
        question="How are sales?",
    )

    save_audit_event(event)
    clear_audit_events()
    restored = get_audit_event("workflow-1")

    assert log_path.exists()
    assert restored is not None
    assert restored["question"] == "How are sales?"
    assert restored["statuses"] == {"sales": "success"}

