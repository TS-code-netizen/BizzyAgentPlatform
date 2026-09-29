from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AS_OF_DATE = "2026-09-23"


def _resolve_data_dir() -> Path:
    configured = os.getenv("BIZZY_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    # Look for full dataset in workspace parent folders or fallback to local backend data
    candidates = [
        ROOT.parents[1] / "BizzyData.worktrees" / "explanation-request-clarification" / "data" / "demo",
        ROOT.parents[1] / "BizzyData" / "data" / "demo",
        ROOT.parent / "BizzyData" / "data" / "demo",
    ]
    return next((path for path in candidates if path.exists()), ROOT / "data" / "demo")


DATA_DIR = _resolve_data_dir()


def as_of_date() -> date:
    """Fixed reporting cutoff for the demo; wall-clock dates would break the frozen scenario numbers."""
    return date.fromisoformat(os.getenv("BIZZY_AS_OF_DATE", DEFAULT_AS_OF_DATE))

def _read_csv(name: str) -> list[dict[str, str]]:
    file_path = DATA_DIR / name
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sales() -> list[dict[str, str]]:
    return _read_csv("sales.csv")


def load_inventory() -> list[dict[str, str]]:
    return _read_csv("inventory.csv")


def load_invoices() -> list[dict[str, str]]:
    return _read_csv("invoices.csv")


def load_customer_enquiries() -> list[dict[str, str]]:
    return _read_csv("customer_enquiries.csv")

# Add this at the bottom of backend/tools/demo_data.py

def get_db() -> duckdb.DuckDBPyConnection:
    """Creates an in-memory DuckDB connection pointing directly to CSV datasets."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW feedback AS SELECT * FROM '{DATA_DIR / 'customer_feedback.csv'}';")
    con.execute(f"CREATE VIEW enquiries AS SELECT * FROM '{DATA_DIR / 'customer_enquiries.csv'}';")
    con.execute(f"CREATE VIEW returns AS SELECT * FROM '{DATA_DIR / 'returns.csv'}';")
    con.execute(f"CREATE VIEW refunds AS SELECT * FROM '{DATA_DIR / 'refunds.csv'}';")
    con.execute(f"CREATE VIEW sales AS SELECT * FROM '{DATA_DIR / 'sales.csv'}';")
    con.execute(f"CREATE VIEW products AS SELECT * FROM '{DATA_DIR / 'products.csv'}';")
    return con


def analyze_customer_complaints() -> list[dict]:
    """Calculates defect complaint rates and total refund financial impact per product."""
    con = get_db()
    query = """
    WITH product_sales AS (
        SELECT product_id, SUM(quantity) AS total_units_sold
        FROM sales
        GROUP BY product_id
    ),
    complaint_stats AS (
        SELECT
            f.product_id,
            COUNT(*) AS total_complaints,
            SUM(f.affected_quantity) AS defective_units,
            COUNT(DISTINCT f.return_id) AS total_returns
        FROM feedback f
        WHERE f.feedback_type = 'complaint'
        GROUP BY f.product_id
    ),
    refund_stats AS (
        SELECT
            r.product_id,
            SUM(ref.amount) AS total_refund_amount_sgd
        FROM returns r
        JOIN refunds ref ON r.return_id = ref.return_id
        GROUP BY r.product_id
    )
    SELECT
        p.product_id,
        p.product AS product_name,
        ps.total_units_sold,
        COALESCE(cs.total_complaints, 0) AS complaint_count,
        COALESCE(cs.defective_units, 0) AS defective_units,
        COALESCE(cs.total_returns, 0) AS return_count,
        ROUND((COALESCE(cs.defective_units, 0) * 100.0 / NULLIF(ps.total_units_sold, 0)), 4) AS complaint_rate_pct,
        COALESCE(rs.total_refund_amount_sgd, 0.0) AS total_refund_sgd
    FROM products p
    JOIN product_sales ps ON p.product_id = ps.product_id
    LEFT JOIN complaint_stats cs ON p.product_id = cs.product_id
    LEFT JOIN refund_stats rs ON p.product_id = rs.product_id
    ORDER BY complaint_rate_pct DESC
    LIMIT 5;
    """
    rows = con.execute(query).fetchall()
    cols = [desc[0] for desc in con.description]
    results = [dict(zip(cols, row)) for row in rows]
    con.close()
    return results


def analyze_customer_enquiries_sla() -> list[dict]:
    """Analyzes customer support SLA and identifies unanswered high-intent leads."""
    con = get_db()
    query = """
    SELECT
        status,
        COUNT(*) AS total_count,
        COUNT(CASE WHEN intent = 'lead' AND status = 'unanswered' THEN 1 END) AS unanswered_leads,
        COUNT(CASE WHEN intent_strength = 'high' AND status = 'unanswered' THEN 1 END) AS high_intent_missed
    FROM enquiries
    GROUP BY status;
    """
    rows = con.execute(query).fetchall()
    cols = [desc[0] for desc in con.description]
    results = [dict(zip(cols, row)) for row in rows]
    con.close()
    return results
