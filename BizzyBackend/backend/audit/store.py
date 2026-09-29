from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.models.agent import AgentResponse
from backend.security.guard import action_decision

_EVENTS: dict[str, dict[str, object]] = {}
_LOCK = Lock()


class AuditUnavailable(RuntimeError):
    pass


class DecisionConflict(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _table(name: str):
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
        config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1})).Table(name)


def _encoded(event: dict) -> str:
    payload = json.dumps(event, ensure_ascii=False, allow_nan=False)
    if len(payload.encode("utf-8")) > 350_000:
        raise AuditUnavailable("Evidence exceeds the audit record size limit.")
    return payload


def _log_path() -> Path | None:
    configured = os.getenv("BIZZY_AUDIT_LOG")
    return None if not configured else Path(configured).expanduser()


def build_audit_event(
    workflow_id: str,
    user: str,
    results: list[AgentResponse],
    decision: str,
    question: str | None = None,
) -> dict[str, object]:
    actions = []
    for result in results:
        for action in result.recommended_actions:
            policy = action_decision(action)
            actions.append({
                "action_id": f"{workflow_id}:{len(actions)}", "agent": result.agent,
                **action.model_dump(mode="json"), "policy": policy,
                "state": "blocked" if decision == "blocked" else ("pending" if policy == "approval_required" else "read_only"),
            })
    return {
        "workflow_id": workflow_id,
        "user": user,
        "question": question if os.getenv("BIZZY_RECORD_QUESTIONS", "true") == "true" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agents": [result.agent for result in results],
        "statuses": {result.agent: result.status.value for result in results},
        "decision": decision,
        "evidence_count": sum(len(result.evidence) for result in results),
        "actions": actions,
        "results": [result.model_dump(mode="json") for result in results],
        "revision": 0,
        "decisions": [],
    }


def save_audit_event(event: dict[str, object]) -> None:
    workflow_id = str(event["workflow_id"])
    payload = _encoded(event)
    table_name = os.getenv("BIZZY_AUDIT_TABLE")
    if table_name:
        try:
            _table(table_name).put_item(Item={"workflow_id": workflow_id, "revision": 0, "payload": payload},
                ConditionExpression="attribute_not_exists(workflow_id)")
            return
        except (ClientError, BotoCoreError) as exc:
            raise AuditUnavailable("Audit persistence failed.") from exc
    with _LOCK:
        path = _log_path()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        _EVENTS[workflow_id] = deepcopy(event)


def get_audit_event(workflow_id: str) -> dict[str, object] | None:
    table_name = os.getenv("BIZZY_AUDIT_TABLE")
    if table_name:
        try:
            item = _table(table_name).get_item(Key={"workflow_id": workflow_id}, ConsistentRead=True).get("Item")
            return json.loads(item["payload"]) if item else None
        except (ClientError, BotoCoreError, ValueError, KeyError) as exc:
            raise AuditUnavailable("Audit retrieval failed.") from exc
    with _LOCK:
        event = _EVENTS.get(workflow_id)
        if event is not None:
            return deepcopy(event)
        path = _log_path()
        if path is None or not path.exists():
            return None
        matched = None
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                candidate = json.loads(line)
                if str(candidate.get("workflow_id")) == workflow_id:
                    matched = candidate
        if matched is not None:
            _EVENTS[workflow_id] = matched
            return deepcopy(matched)
        return None


def clear_audit_events() -> None:
    with _LOCK:
        _EVENTS.clear()


def decide_action(action_id: str, actor: str, decision: str, reason: str) -> dict:
    workflow_id, separator, index = action_id.rpartition(":")
    if not separator or not index.isdigit() or decision not in {"approved", "rejected"}:
        raise KeyError(action_id)
    event = get_audit_event(workflow_id)
    if event is None:
        raise KeyError(action_id)
    position = int(index)
    if position >= len(event["actions"]) or event["actions"][position]["action_id"] != action_id:
        raise KeyError(action_id)
    action = event["actions"][position]
    if action["state"] == decision and action.get("decided_by") == actor:
        return action
    if action["state"] != "pending" or event["decision"] == "blocked":
        raise DecisionConflict("Action is not pending approval.")
    revision = event["revision"]
    timestamp = datetime.now(timezone.utc).isoformat()
    action.update(state=decision, decided_by=actor, decided_at=timestamp)
    event["decisions"].append({"action_id": action_id, "decision": decision, "actor": actor, "reason": reason, "at": timestamp})
    event["revision"] = revision + 1
    payload = _encoded(event)
    table_name = os.getenv("BIZZY_AUDIT_TABLE")
    if table_name:
        try:
            _table(table_name).update_item(Key={"workflow_id": workflow_id},
                UpdateExpression="SET payload = :payload, revision = :next",
                ConditionExpression="revision = :previous",
                ExpressionAttributeValues={":payload": payload, ":next": revision + 1, ":previous": revision})
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise DecisionConflict("Another decision was recorded; reload the workflow.") from exc
            raise AuditUnavailable("Approval persistence failed.") from exc
        except BotoCoreError as exc:
            raise AuditUnavailable("Approval persistence failed.") from exc
    else:
        with _LOCK:
            current = _EVENTS.get(workflow_id)
            if current is None or current["revision"] != revision:
                raise DecisionConflict("Another decision was recorded; reload the workflow.")
            path = _log_path()
            if path:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(payload + "\n")
            _EVENTS[workflow_id] = event
    return deepcopy(action)
