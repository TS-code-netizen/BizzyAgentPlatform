import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tools import demo_data

client = TestClient(app)


@pytest.fixture
def packaged_finance(tmp_path, monkeypatch):
    archive_path = Path(__file__).resolve().parents[1] / "docker/bizzydata-demo.tar.gz"
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            assert member.isfile() and Path(member.name).name == member.name
            (tmp_path / member.name).write_bytes(archive.extractfile(member).read())
    monkeypatch.setattr(demo_data, "DATA_DIR", tmp_path)


@pytest.mark.parametrize("report_type", ["profitability", "operating_expenses", "cash_flow", "receivables"])
def test_packaged_reports(packaged_finance, report_type):
    response = client.get("/api/v1/finance/report", params={"report_type": report_type})
    assert response.status_code == 200
    report = response.json()
    assert report["as_of_date"] == "2026-09-23"
    assert report["currency"] == "SGD"
    assert report["start_date"] == (None if report_type == "receivables" else "2026-09-01")
    evidence = {item["metric"]: item["value"] for item in report["evidence"]}
    if report_type == "receivables":
        assert evidence["overdue_outstanding_sgd"] == 209354
        assert "receivables_ageing_sgd" in evidence
    else:
        assert evidence["cash_bridge_reconciled"] is True


@pytest.mark.parametrize("params", [
    {"report_type": "unknown"},
    {"report_type": "profitability", "start_date": "2026-09-24"},
    {"report_type": "profitability", "as_of_date": "2026-09-24"},
    {"report_type": "profitability", "start_date": "2022-01-01"},
    {"report_type": "receivables", "start_date": "2026-09-01"},
    {"report_type": "cash_flow", "as_of_date": "invalid"},
])
def test_invalid_periods(params):
    assert client.get("/api/v1/finance/report", params=params).status_code == 422


def test_missing_finance_data(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_data, "DATA_DIR", tmp_path)
    response = client.get("/api/v1/finance/report?report_type=profitability")
    assert response.status_code == 503
    assert "evidence" not in response.json()


def test_authentication_required(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COGNITO_ISSUER", "https://cognito-idp.ap-southeast-1.amazonaws.com/example")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "example")
    assert client.get("/api/v1/finance/report?report_type=profitability").status_code == 401


def test_full_history_cash_bridge(packaged_finance):
    response = client.get("/api/v1/finance/report?report_type=cash_flow&start_date=2023-01-01")
    assert response.status_code == 200
    evidence = {item["metric"]: item["value"] for item in response.json()["evidence"]}
    assert evidence["net_profit_before_tax_sgd"] == 2762004.94
    assert evidence["closing_cash_sgd"] == 3299719.68
