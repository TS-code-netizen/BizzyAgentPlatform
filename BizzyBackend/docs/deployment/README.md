# BizzyBee deployment discovery

Historical discovery snapshot. Current accepted decisions, implementation and approval boundaries are in [PLAN.md](PLAN.md); validation results are in [COMPLETION.md](COMPLETION.md).

Discovery date: 2026-09-26. Status: discovery only; no infrastructure or application implementation, provisioning, deployment, IAM change, budget change, or remote repository configuration performed.

This directory is the authoritative location for shared deployment documentation. Architecture, cost estimates, IAM policies, workflows, and operational runbooks remain pending the decisions below.

## Reference material

Read the text and tables of both supplied documents:

- BizzyBee_AI_Delivery_Measurement_and_Controls.docx
- BizzyBee_AI_Master_Team_Reference_23_Sep_2026.docx

Their service list is intent, not evidence of deployment. The current three-repository arrangement supersedes the older single-repository example. Keep one FastAPI deployment with logical agent modules; deterministic calculations and policy enforcement; synthetic data; no autonomous payments. Document examples are not measured implementation results.

## Verified repository state

Repositories are under `/Users/sonny/Desktop/Code/BizzyBee/`, not directly under `/Users/sonny/Desktop/Code/`.

| Repository | Local and remote main at inspection | Notes |
| --- | --- | --- |
| BizzyBackend | 88199d032f2e1c40904bf0e03ac9303c35bcdb14 | Clean before this report; one backup stash; existing feature worktree preserved |
| BizzyFrontend | 20ed7475efab7a1391c0948c208c96d301468630 | Clean; one backup stash; existing feature worktree preserved |
| BizzyData | 6e07ba26732e3c5eff561bef88128e266f16ad26 | Clean; no stashes listed |

GitHub authentication works outside the network sandbox as `pyiesone`, with ADMIN access to all three private repositories. The initial sandbox authentication error was not a real authentication failure. No re-login is required based on this inspection. Open PRs: frontend #4 (interactive dashboard integration), data #1 (WIP sample datasets); no open backend PRs. Do not overwrite concurrent frontend work.

No repository AGENTS.md files, Actions workflows, Terraform configuration, Terraform state, or provider lockfile were found. Backend `infra/` contains only a placeholder. Remote state locations remain unknown; absence of local state is not proof that cloud resources do not exist.

## Application findings

- Backend entry point: `backend.main:app`; Python 3.12 container; port 8000; `/health` reports process health only, not dataset or dependency readiness.
- Queen still imports `ChatOpenAI` and uses `gpt-4o-mini` after deterministic routing fails. Exceptions silently route to Customer; no explicit timeout, bounded retry configuration, usage telemetry, or Bedrock integration is present in that path. BEDROCK_MODEL_ID in the environment example is not evidence of integration or availability.
- Business calculations use deterministic Python/DuckDB tools. Preserve the fixed reporting date 2026-09-23.
- API has no authenticated identity boundary. Query `user` is caller-controlled. No implemented approve/reject endpoints or durable approval state were found.
- Guard recognizes RED labels and selected purchasing action types. It needs an explicit action-policy allowlist/denylist so a dangerous action mislabeled GREEN cannot bypass policy. No real payment execution integration was found.
- Audit storage is process-local with optional JSONL. Container-local JSONL is not durable across replacement or shared across replicas. Records include raw questions, action summaries and evidence counts rather than complete evidence snapshots; retention and privacy policy need decisions.
- CORS origins are configurable and default to localhost. HTTPS production origins must be explicit; CORS is not authentication.
- Frontend entry point is `src/main.tsx` -> `src/App.tsx`. Production API configuration is `VITE_API_BASE_URL`; `/api` proxy exists only for development. Commands: `npm ci`, `npm run lint`, `npm run build`, `npm run test:integration` (requires running services).
- UI offers English, Tamil, Mandarin, Bahasa Melayu and Hindi. Deterministic backend localization currently supports English/Chinese, not validated five-language coverage.
- Existing backend tests use pytest; routing benchmark is opt-in. Application tests/builds/container smoke tests were not run in this discovery pass; do not interpret inspection as a passing release gate.

## Dataset validation

Ran `python3 BizzyData/scripts/validate_datasets.py`: PASS, 21 CSV files, 498535 records, 59639121 bytes, date coverage and all scenario expectations verified. No regeneration performed.

Backend archive pins the same dataset commit. All nine actual CSV archive members match the current source files by SHA-256. The archive also contains macOS AppleDouble metadata entries, which should be excluded on regeneration. Packaging includes a subset, not all 21 tables; it does not yet provide full ledger-based financial analysis. No release checksum/provenance manifest was found. Container execution has not been verified.

## AWS discovery and blockers

Verified default-profile caller before account inspection: account `524097108092`, IAM user `sonny1`. This is not an SSO role session. Do not assume it is the intended deployment account.

`organizations:DescribeOrganization` returned AWSOrganizationsNotInUseException: this account is not a member of an AWS Organization. It cannot substantiate the requested organization-wide consolidated budget. Obtain the actual management-account session, or explicitly revise the requirement; do not create an Organization implicitly.

Read-only Singapore inventory found no App Runner services; two unrelated MintCommerce ECR repositories; an unrelated WildRydes Amplify app; existing GitHub OIDC provider `arn:aws:iam::524097108092:oidc-provider/token.actions.githubusercontent.com`; no clearly named BizzyBee deployment/runtime roles; unrelated MintCommerce secret identifiers; no completed CloudFormation stacks returned by the limited status query. Existing unrelated resources must not be reused or changed without approval. This is not an exhaustive all-region inventory.

Installed AWS CLI is 2.4.15 and has no Bedrock command. Bedrock quota listing works through Service Quotas, but quota presence does not establish model entitlement or inference access. Model/profile availability, onboarding, inference destinations, and restrictions remain unverified. Use a current isolated CLI/SDK for remaining discovery; do not invoke or activate a model.

AWS now closes App Runner to new customers. No services in Singapore does not prove account eligibility either way. Do not finalize App Runner Terraform before eligibility is established. AWS identifies ECS Express Mode as an alternative, with charges for underlying Fargate, load balancer and networking resources; its fixed costs require a separate Singapore estimate against the USD 50 total budget.

Source: https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html

## Existing budget is not organization-wide evidence

Account budget `My Monthly Cost Budget`: COST, MONTHLY, USD 50, start 2026-05-01, configured end 2087-06-15. AWS reported actual USD 1.10 and forecast USD 1.299, updated 2026-09-26 19:59:39 +08:00. This is the existing account budget's calculation, not verified organization-wide MTD spend. Its actual amount is below USD 25/40/50, but organization headroom remains unknown.

Existing notifications are actual >85%, actual >100%, forecast >100%, not the requested 50/80/100 actual thresholds. The old CLI response omits cost/filter calculation fields, so credits, refunds, taxes, support, discounts and full scope cannot safely be inferred from it. Read the complete configuration with a current SDK before proposing an exact update. Do not duplicate this budget blindly.

Pending proposal: recurring MONTHLY COST USD 50 in the verified payer account, no account/service/region/tag filters, actual notifications at 50/80/100% and forecast >100%, recipients and SNS undecided, no automatic budget actions. Exact comparison semantics and cost calculation must be included in the reviewable configuration. Decide whether credits/refunds reduce the monitored amount; include taxes/support and explain discounts explicitly rather than relying on defaults.

Budgets are delayed alerts, not spending caps. Unrelated organization workloads consume the same allowance. No deployment cost/headroom claim is approved or verified yet.

Source: https://docs.aws.amazon.com/cli/latest/reference/budgets/describe-budgets.html

## Required decisions and minimum discovery access

| Input | Existing evidence and why needed | Minimum next access |
| --- | --- | --- |
| Deployment account/profile | Confirm 524097108092 or provide intended SSO profile; prevents wrong-account changes | STS identity plus scoped service List/Describe/Get metadata |
| Organization payer/profile | Current account is standalone; needed for consolidated scope and spend | organizations:DescribeOrganization, organizations:ListAccounts, budgets:ViewBudget, ce:GetCostAndUsage; current budget/billing-view metadata read access |
| Region and audience | Propose ap-southeast-1; confirm demo/staging/production, public vs invited users, uptime window | Decision only initially |
| Authentication and approvals | No auth or approval persistence; public backend must not expose paid inference unauthenticated | Choose identity provider and authorized approver roles; scoped provider metadata reads if existing |
| Audit durability | Memory/JSONL is insufficient for multi-instance durable approvals | Decide retention, persistence requirement and storage approach; no storage provisioning yet |
| Domain/DNS | Unknown; affects TLS, origins and frontend API endpoint | Hosted-zone list/get only if using existing DNS; changes require later approval |
| Roles and state | OIDC provider exists; deployment/runtime roles and state backend unidentified | iam:GetOpenIDConnectProvider, iam:GetRole and scoped policy reads; existing state bucket metadata/access only after identification |
| Model and geography | Bedrock not integrated; model preference/residency unknown | Bedrock model/profile availability List/Get and Service Quotas reads; no InvokeModel, Marketplace subscription or activation yet |
| Budget recipients/calculation | Existing account budget differs; need email addresses and whether SNS is required | Decisions and budget metadata read access; update permission only after exact approval |
| Secret identifiers | Only unrelated secret names found | Supply names/ARNs only if application requires them; DescribeSecret only for discovery, no secret values |
| Private cross-repository delivery | All repos private; existing bundled data can avoid runtime/release cross-repo fetch | Decide approved release-artifact transfer or GitHub App with Contents read only on BizzyData; no broad PAT assumption |
| GitHub deployment controls | ADMIN access verified; environment protection not yet inspected | Read environment/ruleset settings; writes and environment approvals remain separate authorization |

Never paste secret values. Bedrock role credentials require no OpenAI or Anthropic API key.

## Next implementation boundary

After the above decisions, prepare isolated changes: small Bedrock adapter with mocked tests; fail-closed action policy and chosen identity/persistence integration; data provenance; separate CI and trusted-ref deployment workflows; Terraform bootstrap/runtime separation; costed resource inventory and reviewed plan. Prefer Actions-controlled frontend deployment for a single explicit CI gate, subject to checking existing remote integration settings. No Cognito or RDS resources without actual application integration.

All external changes remain approval-gated. No branches, commits, pushes, deployments, paid inference or budget mutations were performed. Only this discovery document was added locally.
