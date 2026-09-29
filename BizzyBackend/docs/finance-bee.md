# Finance Bee — scoped implementation

The Finance implementation and its reporting integration do not change other Bee implementations, Queen routing, Guard rules, shared agent response schemas, dataset contents or AWS resources. Finance-only localization preserves English summaries for non-receivables reports. Integration adds a dedicated authenticated Finance endpoint and frontend panel.

## Capabilities

- Existing finance summary contract remains overdue invoice count/outstanding amount, fixed default cutoff 2026-09-23.
- With payments.csv present, reconstruct invoice balances from issue/payment dates, ignoring future payments. Return not-due, 1–30, 31–60, 61–90 and over-90-day buckets plus outstanding exposure by customer ID. Due today is not overdue. Without dated payments, the existing cutoff snapshot still works, but historical dates fail explicitly.
- Profitability: ledger net revenue after returns, COGS, gross profit, operating expenses, profit before tax and margins. Zero/non-positive revenue produces undefined margins, not division by zero or an invented percentage.
- Operating expenses: account-code breakdown from ledger postings. Depreciation is an expense, not a cash payment.
- Cash: opening balance plus dated receipts minus dated payments equals closing cash. Opening-balance journals are excluded from period cash flow; movements are grouped by source. Never sum supporting CSV totals on top of ledger balances.
- Month-to-date default, last calendar month and year-to-date phrases; explicit period_start/as_of supported by the Python Finance function. Comparison is the preceding equal-length interval, labelled with dates, not a falsely labelled calendar month. Comparisons outside data coverage are omitted. Selected unsupported date phrases return clarification instead of silently using this month; this is not a general natural-language date parser.
- SGD only; Decimal calculations. Duplicate records, unknown accounts, non-finite/negative monetary fields, invalid dates, mixed currencies, unbalanced journals and missing files fail closed. Connections/files are closed. Numeric evidence remains compatible with the existing response schema.
- Receivable reminder proposals retain the existing AMBER action; no reminder is proposed with zero overdue invoices. New ledger analyses are read-only and introduce no new Guard action names or executor.

## Verified dataset baseline

Full-history interval 2023-01-01 through 2026-09-23, SGD:

| Metric | Value |
| --- | ---: |
| Net revenue | 10,087,199.00 |
| Gross profit | 3,902,708.30 |
| Operating expenses | 1,140,703.36 |
| Profit before tax | 2,762,004.94 |
| Opening cash | 500,000.00 |
| Net cash flow | 2,799,719.68 |
| Closing cash | 3,299,719.68 |
| Overdue invoices | 528 |
| Overdue outstanding | 209,354.00 |

These were recomputed locally and compared to scenario_expectations.csv; they are not current real-world business figures. The ledger contains 273,036 lines. Existing source CSVs were not regenerated.

## Tests

`PYTHONPATH=. BIZZY_FINANCE_DATA_DIR=../BizzyData/data/demo python -m pytest -q tests/test_finance_bee.py tests/test_finance_analysis.py`

Includes balanced-ledger reconciliation, opening entries, refund impact, prior periods, future postings/payments, partial payments, ageing boundaries, invalid records, missing files, margins and Finance-only localization. The sibling-checkout scenario test remains opt-in. `tests/test_finance_reports.py` exercises the committed archive without sibling checkouts, including full-history reconciliation, validation and authentication. No inference or cloud calls are needed.

## Explicit integration boundaries

1. The archive now includes accounts.csv/accounting_ledger.csv/payments.csv from the existing pinned dataset commit. Packaging reads committed Git blobs, not a moving branch or working-tree files. Archive/member checksums are refreshed; existing members remain unchanged. Supplier/expense/opening CSVs already reconcile through ledger postings; their totals must not be added again.
2. Queen routing was not changed: terms such as profit may be sent to Sales or need Bedrock routing. Use the dedicated Finance panel/API for explicit reporting. API `/finance/summary` retains its signature and overdue summary contract.
3. Advisor and Guard were not changed. Advanced Finance evidence is available as structured data; no promise that other Bees interpret every new metric. Full new-language summaries are not implemented; the Finance-only localization guard preserves amounts and intent through English fallback.
4. Monthly expense recognition follows actual posting dates. A month-to-date report can omit expenses recognized at month end; it is not a forecast or accrual estimate beyond the ledger.
5. Historical recorded supplier payments/refunds are evidence only, never authorization to make payments. No autonomous financial action exists.

## Reporting integration

`GET /api/v1/finance/report?report_type=profitability&start_date=2026-09-01&as_of_date=2026-09-23`

- Report types: profitability, operating_expenses, cash_flow, receivables. Dates are ISO dates within 2023-01-01 through 2026-09-23. Default reporting date is fixed at 2026-09-23; non-receivables start defaults to that reporting month's first day. Receivables rejects start_date rather than silently ignoring it.
- Response: report_type, start_date (null for receivables), as_of_date, currency, summary and typed Evidence entries. Source files, metric periods and reconciliation status are carried in evidence. No recommendation execution or approval-state changes occur.
- Existing Cognito authentication applies through the parent API router. Invalid inputs return 422; unavailable/invalid financial data returns 503 with no fabricated totals. No new permissions or model calls.
- Frontend Finance panel requests reports only on submission; dates and report type are explicit. Requests use existing bearer-token/30-second timeout handling, cancellation and stale-response protection. Failures clear old figures; undefined margins display Not available. Tables preserve account/customer IDs. Summaries currently remain English.
- Frontend validation: npm run lint, npm run build, npm run test:finance, npm run test:contract and npm run test:dashboard. Contract snapshot adds only the Finance report model and route.
- Local packaging: python scripts/package_data.py ../BizzyData followed by python scripts/verify_data.py. BIZZY_DATA_REF is unchanged. Repeating packaging should yield the same archive checksum.
- Deployment remains separately approved. Release backend/archive first, smoke-test all four authenticated reports, then release frontend. Roll back frontend first and then backend using the existing deployment runbook; no data migration is involved. Before backend rollout, the new frontend panel would receive 404 from older backends; existing views remain usable.

No changes are made to other Bees or their shared routing. The direct report endpoint does not create an application audit event; adding audited read-report requests is a separate Audit integration decision.
