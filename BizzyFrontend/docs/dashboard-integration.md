# Dashboard integration on current contracts

Branch: `feat/dashboard-current-contracts`, based on main `210fba7`. PR #4 (`7c1da8f`) was used only as a design reference. Its branch, commits, title, body and merge state were not modified. No merge/rebase of PR #4 was performed.

## Included

- Responsive sidebar, welcome banner, navigation, live backend KPI cards and quick question selection, adapting the interactive dashboard direction to current main.
- All eight logical Bees with selectable findings, structured evidence, source labels and response-derived states. No simulated streaming progress or invented execution status.
- Existing sales/inventory panels, alerts, finance-derived KPIs, language codes and honest localization fallback messages retained.
- Existing Cognito AuthGate, token-bearing requestJson client, request timeouts, identity checks and ApprovalControls retained unchanged. No body-supplied user identity added.
- Current-workflow audit retrieval only, with retry on failure. The UI explicitly distinguishes an unconfirmed query-response summary from a retrieved audit record.
- New queries clear old results/audit immediately, preventing failed requests from leaving stale approval controls visible. RED/blocked recommendations remain non-approvable; approvals never imply business execution.

## Deliberately deferred

No `GET /api/v1/audit` listing request, trace_id contract, fabricated audit fields, backend API/storage change or full audit-history browsing. That requires a separate authorization-aware paginated API design. Browser view is not an authorization boundary: backend enforcement remains authoritative.

## Verification

- Lint, TypeScript/Vite production build and existing contract check.
- Seven dependency-free Node tests (`npm run test:dashboard`) covering role inventory, loading/error/partial states, missing results, blocked policy and audit persistence confirmation; included in CI.
- Headless Chrome against isolated local frontend/backend with inference disabled: eight agents; customer evidence; real synthetic audit retrieval; owner reason/rejection; simulated non-approver UI; failed-query stale-control clearing; no unsupported audit-list requests; no page errors; mobile width 390 with no horizontal overflow. The non-approver UI case mocks `/me`, not production security.
- Screenshots inspected at desktop/mobile sizes. This is not a fresh deployed Cognito acceptance test. No cloud calls, paid inference or deployment were performed for the UI tests.

The existing default complaint question may depend on Bedrock because current heuristic routing matches singular complaint but not plural complaints. The local test deliberately used “Show customer feedback and complaint trends” to exercise Customer Bee without inference. Backend routing was not changed in this frontend task.

The user approved committing/pushing this separate branch and opening a new PR. PR #4 remains unchanged. Merge and deployment require separate explicit approval.
