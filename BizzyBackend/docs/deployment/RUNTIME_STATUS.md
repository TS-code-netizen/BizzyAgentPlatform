# Runtime deployment status

## Approved Bedrock enablement — current configuration

The user approved the exact two-update plan and conditional alias promotion. Reverified account, six APAC destinations and an exact resource-change match to the reviewed plan before applying. Terraform: **0 added, 2 updated, 0 destroyed** (runtime inline IAM policy and Lambda model environment). No GitHub roles or streaming/activation permissions added.

Published version **2** uses the unchanged image and `apac.amazon.nova-micro-v1:0`, provider `bedrock`. Candidate readiness returned 200 and fixed cutoff 2026-09-23. Conditionally promoted live from **1 to 2** using the recorded alias RevisionId. Live readiness passed and unauthenticated `/api/v1/me` remained 401. No extra paid model request was executed during enablement. Runtime-role inference through an authenticated user question remains to be verified; the earlier paid smoke used operator credentials.

Version 1 is retained as the inference-disabled rollback target. Rollback must use a fresh conditional alias update; it does not remove the added IAM permission. Normal invited-user traffic can now incur model charges when heuristic routing falls through. No autonomous business-action execution is enabled. Frontend release.json still describes its earlier build-time disabled model snapshot; it is not current backend status.

Reproduce the approved configuration for future plans with `-var-file=terraform.tfvars.example`, the published `image_digest`, and **`-var='enable_inference=true'`**. Defaults remain safely disabled and must not silently replace the approved live inputs. Private promotion/rollback evidence is retained in `/private/tmp/bizzybee-bedrock-promotion.json` and `/private/tmp/bizzybee-bedrock-prior-alias.json`; these are not committed.

## Single approved Bedrock smoke test

After the user reported authenticated workflow checks passed, the user explicitly approved one paid smoke request. Verified account 524097108092 and the exact six previously reviewed APAC destinations before invocation. Ran the existing classifier once via the local operator's AWS credentials, with maximum output 128 tokens and total SDK attempts 1, using a synthetic stock question. No IAM or application configuration was changed.

Result: `apac.amazon.nova-micro-v1:0` returned the expected validated `["inventory"]` route; latency 507 ms, input 74 tokens, output 7 tokens, no fallback. Application model provider was verified disabled before the test and was not changed. This confirms operator access and one routing case, not Lambda role access, five-language quality or general model accuracy. Runtime inference enablement and exact model IAM permissions require separate approval. User-reported authenticated acceptance is distinct from agent-executed tests; no passwords or user sessions were used here.

## Approved CORS correction

The supplied HAR exposed OPTIONS requests returning 401 from the JWT-protected ANY proxy route. Earlier CORS verification checked headers but not successful preflight status; it was insufficient. No HAR credentials were replayed or copied into the repository.

After explicit approval, applied only `aws_apigatewayv2_route.preflight`: `OPTIONS /api/v1/{proxy+}`, authorization NONE, existing backend integration. Terraform reported **1 added, 0 changed, 0 destroyed**. Business GET/POST routes retain JWT authorization; allowed origins remain unchanged.

Verified preflight HTTP 200 with the exact allowed origin for sales, inventory, finance, business health, alerts, query and approval paths. Unauthenticated GET/POST remain 401; untrusted origins receive no allow-origin header. Initial verification saw one 503 on query preflight; a subsequent lower-rate pass succeeded on all seven paths without retries. Its cause was not established; no concurrency/throttling settings were changed. Final Terraform plan shows no changes.

Authenticated browser workflow acceptance remains pending user retry. Reload the frontend and sign in again if the session expired. If errors persist, capture a sanitized HAR; do not share bearer tokens, cookies or authorization codes. The prior transient 503 remains an observation rather than a claimed resolved capacity issue.

## Frontend and invitations update

The user subsequently approved frontend publication and the four invitations. Amplify deployment job **3 SUCCEED** published https://poc.d1w9q0ck4cdi9s.amplifyapp.com . Earlier unpublished/pending-invitation statements below describe the infrastructure-only stage.

- Production API/Cognito settings were supplied at build time; no development proxy or provider key is used. `npm ci`, lint, contract checks and TypeScript/Vite production build passed; npm audit reported zero vulnerabilities.
- Archive retained at `/private/tmp/bizzybee-frontend-release/frontend.zip`, SHA-256 `e06d3dfb6074a2a2ab215408ef6d636eb41bd946e778b4c50ccb319465275472`. Release metadata identifies dirty working-tree base commits rather than falsely claiming a clean Git release.
- Initial upload failed because system Python lacked trusted CA roots. Deployment helper now explicitly uses the botocore CA bundle (or AWS_CA_BUNDLE), with TLS verification retained. Incomplete pending jobs 1 and 2 were stopped; job 3 uploaded the same archive and succeeded. No certificate verification bypass was used.
- Live root and release metadata returned 200. Every published JS/CSS asset matched its local build SHA-256. Cognito OIDC discovery and hosted authorization/login page returned 200 with the configured callback and PKCE parameters.
- Cognito accepted creation/email-invitation requests for `sonepyie@gmail.com`, `peacemother21@gmail.com`, `tiffanyseah94@gmail.com`, and `e1374579@u.nus.edu`. All four are in FORCE_CHANGE_PASSWORD status. Verified only `sonepyie@gmail.com` belongs to `approvers`; the other three have no groups. Credentials were not printed or stored by this task. Inbox delivery itself is not verified.
- Users must open the app, select sign-in, use their invitation credentials and set a new password. Actual authenticated browser session, approval authorization, audit persistence and sign-out acceptance require the user's login; do not share temporary passwords in chat. No authenticated end-to-end acceptance claim is made yet.
- Bedrock remains disabled. No budget update, GitHub setting change, Git commit/push or paid inference occurred. Next gate is authenticated acceptance testing, followed by separately approved model smoke testing if desired.

September 27, 2026, Singapore. Supersedes earlier pending-runtime statements in the discovery/completion reports. User explicitly approved manual owner-operated deployment, runtime S3 initialization and the reviewed 26-resource apply. Monthly account-wide budget remains USD 50; no budget update performed.

## Applied

- Verified account `524097108092`, available concurrency, published image and completed ECR scan before execution.
- Initialized encrypted S3 state at `bizzybee-poc-tfstate-524097108092/runtime/terraform.tfstate`, native lockfile enabled.
- Regenerated the saved plan and compared all 26 resource change objects against the reviewed local-backend plan: exact match, create-only. Initial inspection scripts stopped before apply because CLI boolean values serialize as strings and the environment block is partly unknown; comparison was corrected without relaxing resource-scope equality.
- Apply completed: **26 added, 0 changed, 0 destroyed**. No additional apply was performed.
- Live backend version `1`, image digest `sha256:5946da98660a6301944182d010efd2e350637e758a087b83d6c82c4373718d09`.
- Post-apply plan initially showed only Amplify custom-header serialization drift. Local configuration was normalized to the exact compact JSON returned by AWS, preserving all three security headers. Final remote-backed plan: **no changes**, exit 0. No AWS update was needed to resolve this drift.

## Identifiers and URLs

| Component | Value |
| --- | --- |
| API | https://5ron8l4p8j.execute-api.ap-southeast-1.amazonaws.com |
| Frontend hosting shell, unpublished | https://poc.d1w9q0ck4cdi9s.amplifyapp.com |
| Amplify app | d1w9q0ck4cdi9s |
| Cognito pool | ap-southeast-1_svEP3R7Ay |
| Public Cognito client | 4jn7chf3m4tesh413tub9pljq2 |
| Cognito domain | https://bizzybee-poc-524097108092.auth.ap-southeast-1.amazoncognito.com |
| Runtime role | arn:aws:iam::524097108092:role/bizzybee-poc-runtime |
| Audit table | bizzybee-poc-audit |

## Verified

- Lambda Active; exact published digest; reserved concurrency 2; model provider disabled.
- `GET /health`: 200; `GET /ready`: 200 with fixed reporting date `2026-09-23`.
- Unauthenticated `GET /api/v1/me`: 401.
- Allowed frontend-origin preflight returns the exact origin; untrusted-origin preflight returns no allow-origin header.
- DynamoDB deletion protection and point-in-time recovery enabled.
- Cognito user list empty: no invitations sent.
- Terraform formatting/validation passed; final refreshed plan has no changes.

## Not performed / next approval boundary

Frontend artifact publication, Cognito invitations, paid inference, budget alert updates and GitHub remote configuration remain unapplied. No GitHub deployment roles were created. Source remains uncommitted and unpushed.

Next: obtain approval to build/publish the frontend using the listed public configuration and invite the four previously specified users, with only the owner in `approvers`. These are external actions, not implied by infrastructure approval. Then verify actual login/callback, identity-bound audit persistence, owner-only approvals and end-to-end connectivity. No claim of authenticated acceptance testing or rollback exercise yet. Alias version 1 is the first release, so there is no previous runtime version to roll back to; stop/disable access rather than invent a rollback target if acceptance fails, subject to approval.

The hosting URL is not a usable application until an artifact is published. Budget usage is delayed, not a spending cap. Operational alarms are console-only pending a separately approved notification channel.
