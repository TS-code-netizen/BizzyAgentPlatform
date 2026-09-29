# BizzyBackend

## POC AWS delivery

See [the authoritative deployment plan](docs/deployment/PLAN.md) for Lambda/Amplify, Cognito login, DynamoDB approvals/audit, Bedrock, CI/CD and approval-gated runbooks. Cloud inference is disabled by default; no third-party model API key is needed. Outside development/test, Cognito and durable audit configuration are mandatory. Existing local uvicorn development remains available.

Minimal BizzyBee backend scaffolding for business-performance monitoring.

## Structure

- `backend/` FastAPI app, agent modules, orchestration, security, audit, models and tools.
- `data/demo/` Synthetic demo datasets.
- `tests/` API scaffolding tests.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## Demo data

The Bees read the synthetic CSVs from the [BizzyData](https://github.com/BizzyBeeAI/BizzyData) repository. Clone it next to this repo, or point `BIZZY_DATA_DIR` at its `data/demo` folder:

```bash
git clone https://github.com/BizzyBeeAI/BizzyData.git ../BizzyData
```

All calculations use the fixed reporting date `BIZZY_AS_OF_DATE=2026-09-23` (see `.env.example`).

## Sales Bee and Inventory Bee

Both Bees are deterministic: numbers come from DuckDB queries over the CSVs, never from an LLM. They return the shared `AgentResponse` contract. When a question is supplied, each Bee selects the relevant analysis instead of returning a fixed full report.

| Bee | Code | Endpoint | What it reports |
| --- | --- | --- | --- |
| Sales | `backend/agents/sales.py`, `backend/tools/sales_tools.py` | `GET /api/v1/sales/summary` | Revenue and units in the last 7 days vs the previous 7, the product driving the change, products that stopped selling, revenue by channel, top 5 products, and gross margin overall and by category |
| Inventory | `backend/agents/inventory.py`, `backend/tools/inventory_tools.py` | `GET /api/v1/inventory/status` | Out-of-stock and at-risk products with their stock, unfulfilled demand, lost and projected lost sales, suggested order quantities, FIFO stock value, stock cover for the top 10 sellers, highest-value stock, and the suppliers with the longest lead times |
| Finance | `backend/agents/finance.py`, `backend/tools/finance_tools.py` | `GET /api/v1/finance/summary` | Overdue invoice count and actual outstanding balance as of the reporting date |

Both endpoints accept `window_days` (1–90, default 7), an optional `as_of` date, an optional natural-language `question`, and `language` (`en` or a `zh` locale). `/api/v1/query` also uses its `language` field for deterministic Chinese routing and localized summaries.

```bash
curl --get http://localhost:8000/api/v1/sales/summary \
  --data-urlencode "question=Which channel generated the most revenue?"

curl --get http://localhost:8000/api/v1/inventory/status \
  --data-urlencode "question=What if demand increases by 20% for PRD001?"
```

A product is **at risk** when its days of cover (current stock ÷ average daily demand over 14 days) are shorter than its supplier lead time. The reorder level alone is not used, because every demo product sits at or below it. When `incoming_qty` is available, the suggested order quantity is `avg_daily_demand × lead_time + reorder_level − current_stock − incoming_qty`. If an expected receipt exists but its quantity is unknown, the estimate is marked provisional and the action changes to `verify_inbound_quantity`; no purchase-order draft should be created until that quantity is confirmed.

With the BizzyData fixture, the two Bees reproduce the flagship story: revenue fell 18% (SGD 70,000 → 57,400), and all of the decline comes from Product A (`PRD001`). Product A is out of stock, with 126 units of unfulfilled demand, which equals SGD 12,600 in lost sales.

For cross-functional questions, Queen passes the original question to both Bees. Advisor links a sales decline to a stockout only when the product, reporting period, timeline, and monetary impact align. It reports this as evidence-supported correlation rather than proven causation. Recommended actions now include a reason, structured parameters, and expected impact; a purchase order remains a draft until Guard returns human approval.

For causal questions such as “Why did sales fall this week?”, Queen first runs Sales. If Sales finds that the declining product stopped selling and recommends checking stock availability, Queen automatically adds Inventory and lets Advisor test the stockout explanation.

Product, channel, margin, stock-risk, supplier, valuation and reorder breakdowns are also returned as structured evidence arrays. Advisor uses these records to identify top sellers at stock risk, high-value/low-velocity inventory, and replenishment priorities instead of parsing display strings.

## Proactive monitoring

The monitoring endpoints turn the same deterministic analysis into dashboard-ready health and alert records:

- `GET /api/v1/sales-inventory/health` returns a 0–100 score, score deductions, headline metrics and priority issues.
- `GET /api/v1/sales-inventory/alerts` returns revenue-decline, stockout, stockout-risk, slow-moving-inventory and data-quality alerts.
- `GET /api/v1/business-health` remains backward-compatible but now returns the same live score instead of a hard-coded value.

The health score starts at 100 and applies capped, transparent deductions for negative revenue movement, stockouts, lead-time stock risk and incomplete source coverage. Every alert includes its threshold and current value. Operational suggestions such as purchase orders remain AMBER drafts requiring human approval.

Guard validates the required product, supplier and quantity fields for controlled purchasing actions and requires approval even if an Agent incorrectly labels such an action GREEN. Every `/api/v1/query` workflow is available from `GET /api/v1/audit/{workflow_id}`. Audit events are process-local by default; set `BIZZY_AUDIT_LOG` to append durable JSONL records that can be recovered after restart.

## Test

```bash
pytest
```

Unit and API tests use the small dataset in `tests/fixtures/demo/`. `tests/test_scenarios.py` checks the frozen numbers in BizzyData's `scenario_expectations.csv`; it is skipped when no BizzyData checkout is found (set `BIZZY_SCENARIO_DATA_DIR` to override the location).

`tests/test_sales_inventory_answers.py` verifies that the 5 Sales, 5 Inventory and 5 Sales+Inventory benchmark questions return the expected question-specific evidence and Advisor synthesis.

`tests/test_health_monitoring.py` verifies dynamic scoring, actionable alert payloads, incomplete-data warnings and both monitoring endpoints.

## Docker

The image is self-contained and does not require a sibling BizzyData checkout:

```bash
docker build -t bizzybackend .
docker run --rm -p 8000:8000 bizzybackend
```

`docker/bizzydata-demo.tar.gz` contains only the CSVs used by the current Bees and is pinned to the source revision recorded in `docker/BIZZY_DATA_REF`. Regenerate this archive when the BizzyData contract changes.

`tests/test_routing_benchmark.py` holds the team's 40 benchmark questions and the Bees Queen should invoke for each. It is opt-in while routing is tuned:

```bash
BIZZY_RUN_ROUTING_BENCHMARK=1 pytest tests/test_routing_benchmark.py
```
