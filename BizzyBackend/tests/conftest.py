from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURE_DATA_DIR = Path(__file__).parent / "fixtures" / "demo"

# Must run before backend modules are imported: API tests read the data directory at import time
# and should never depend on whether a developer has a BizzyData checkout.
os.environ["BIZZY_DATA_DIR"] = str(FIXTURE_DATA_DIR)
os.environ["BIZZY_AS_OF_DATE"] = "2026-09-23"
os.environ["APP_ENV"] = "test"
os.environ["BIZZY_MODEL_PROVIDER"] = "disabled"


@pytest.fixture
def fixture_data_dir() -> Path:
    return FIXTURE_DATA_DIR


@pytest.fixture
def write_csv(tmp_path: Path):
    def _write(name: str, header: str, *rows: str) -> Path:
        (tmp_path / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        return tmp_path

    return _write
