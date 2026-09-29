import json
import time
from types import SimpleNamespace

import jwt
import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.audit import store
from backend.main import app
from backend.models.agent import AgentResponse, RecommendedAction
from backend.orchestration import bedrock
from backend.security import auth
from backend.security.guard import evaluate


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("BIZZY_AUDIT_TABLE", raising=False)
    monkeypatch.delenv("BIZZY_AUDIT_LOG", raising=False)
    monkeypatch.setenv("BIZZY_MODEL_PROVIDER", "disabled")
    store.clear_audit_events()
    yield
    app.dependency_overrides.clear()


def result(action):
    return AgentResponse(agent="inventory", status="success", summary="test", confidence=1, recommended_actions=[action])


@pytest.mark.parametrize("name", ["supplier_payment", "bank_transfer", "change_bank_details", "delete_financial_records", "change_privileged_access", "unknown"])
def test_green_label_cannot_authorize_unknown_or_dangerous_action(name):
    assert evaluate([result(RecommendedAction(type=name))]) == ("blocked", True)


def test_disabled_model_never_constructs_client(monkeypatch):
    monkeypatch.setattr(bedrock, "runtime_client", lambda: pytest.fail("AWS client called"))
    with pytest.raises(bedrock.InferenceUnavailable):
        bedrock.classify("hello")


@pytest.mark.parametrize("payload", ['["sales", "inventory"]', '["admin"]', '["sales", "sales"]', '[]', '{"sales":true}', 'not JSON'])
def test_model_schema_and_tokens(monkeypatch, payload, caplog):
    caplog.set_level("INFO")
    monkeypatch.setenv("BIZZY_MODEL_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "approved-model")
    def converse(**kwargs):
        assert kwargs["modelId"] == "approved-model"
        assert kwargs["inferenceConfig"]["maxTokens"] == 128
        return {"stopReason": "end_turn", "output": {"message": {"content": [{"text": payload}]}}, "usage": {"inputTokens": 20, "outputTokens": 5}}
    monkeypatch.setattr(bedrock, "runtime_client", lambda: SimpleNamespace(converse=converse))
    if payload == '["sales", "inventory"]':
        assert bedrock.classify("private question") == ["sales", "inventory"]
    else:
        with pytest.raises(bedrock.InferenceUnavailable):
            bedrock.classify("private question")
    assert "private question" not in caplog.text
    assert '"input_tokens": 20' in caplog.text


@pytest.mark.parametrize("error", [ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse"), ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse"), ReadTimeoutError(endpoint_url="https://example.invalid")])
def test_bedrock_failure_is_explicit(monkeypatch, error):
    monkeypatch.setenv("BIZZY_MODEL_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "approved-model")
    def converse(**kwargs):
        raise error
    monkeypatch.setattr(bedrock, "runtime_client", lambda: SimpleNamespace(converse=converse))
    with pytest.raises(bedrock.InferenceUnavailable):
        bedrock.classify("hello")


def test_authentication_and_token_validation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "poc")
    monkeypatch.setenv("COGNITO_ISSUER", "https://cognito-idp.ap-southeast-1.amazonaws.com/test")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "jwks_client", lambda issuer: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    client = TestClient(app)
    assert client.get("/api/v1/me").status_code == 401
    claims = {"sub": "actual-user", "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/test", "exp": int(time.time()) + 60, "iat": int(time.time()), "token_use": "access", "client_id": "client"}
    def request(values):
        return client.get("/api/v1/me", headers={"Authorization": f"Bearer {jwt.encode(values, key, algorithm='RS256')}"})
    assert request(claims).json() == {"subject": "actual-user", "approver": False}
    for changes in ({"token_use": "id"}, {"client_id": "other"}, {"exp": 1}, {"iss": "https://wrong"}):
        assert request({**claims, **changes}).status_code == 401


def test_audit_ownership_and_approver_permissions():
    app.dependency_overrides[auth.current_identity] = lambda: auth.Identity("member")
    client = TestClient(app)
    response = client.post("/api/v1/query", json={"question": "Why did sales fall?", "user": "forged-owner"})
    assert response.status_code == 200
    workflow = response.json()["workflow_id"]
    event = client.get(f"/api/v1/audit/{workflow}").json()
    assert event["user"] == "member"
    action = next(action for action in event["actions"] if action["state"] == "pending")
    path = f'/api/v1/actions/{action["action_id"]}'
    assert client.post(path + "/approve", json={"reason": "reviewed"}).status_code == 403
    app.dependency_overrides[auth.current_identity] = lambda: auth.Identity("other")
    assert client.get(f"/api/v1/audit/{workflow}").status_code == 404
    app.dependency_overrides[auth.current_identity] = lambda: auth.Identity("approver", True)
    assert client.post(path + "/approve", json={"reason": "reviewed"}).status_code == 200
    assert client.post(path + "/approve", json={"reason": "retry"}).status_code == 200
    assert client.post(path + "/reject", json={"reason": "changed mind"}).status_code == 409
    saved = client.get(f"/api/v1/audit/{workflow}").json()
    assert len(saved["decisions"]) == 1
    assert saved["results"][0]["evidence"]


def test_dynamodb_approval_compare_and_swap(monkeypatch):
    monkeypatch.setenv("BIZZY_AUDIT_TABLE", "audit")
    event = store.build_audit_event("workflow", "owner", [result(RecommendedAction(type="prepare_invoice_reminders", risk_level="AMBER"))], "approval_required")
    calls = []
    def update_item(**kwargs):
        calls.append(kwargs)
        raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
    monkeypatch.setattr(store, "_table", lambda name: SimpleNamespace(get_item=lambda **kwargs: {"Item": {"payload": json.dumps(event)}}, update_item=update_item))
    with pytest.raises(store.DecisionConflict):
        store.decide_action("workflow:0", "owner", "approved", "reviewed")
    assert calls[0]["ConditionExpression"] == "revision = :previous"


def test_audit_failure_does_not_report_success(monkeypatch):
    monkeypatch.setenv("BIZZY_AUDIT_TABLE", "audit")
    def put_item(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "PutItem")
    monkeypatch.setattr(store, "_table", lambda name: SimpleNamespace(put_item=put_item))
    assert TestClient(app).post("/api/v1/query", json={"question": "sales"}).status_code == 503
