# Runtime review — not approval to apply

**Execution update:** the user subsequently approved this scope. The regenerated remote-backed plan matched all 26 changes and was applied; see [RUNTIME_STATUS.md](RUNTIME_STATUS.md). Do not reuse the old review-only plan.

September 27, 2026, Singapore. Account `524097108092`. Final budget: **USD 50/month account-wide**, including unrelated workloads.

## Plan result and safety boundary

Generated and validated a concrete **26 create / 0 update / 0 destroy** Terraform review plan with the published image:

`524097108092.dkr.ecr.ap-southeast-1.amazonaws.com/bizzybee-poc-backend@sha256:5946da98660a6301944182d010efd2e350637e758a087b83d6c82c4373718d09`

The plan uses a private temporary copy of runtime configuration with only its backend changed to local, avoiding any unauthorized runtime S3 state or lock writes. Files: `/private/tmp/bizzybee-runtime-review/review-only.tfplan` and `plan.txt`. **Do not apply this review plan.** After approval, initialize the real runtime S3 backend, regenerate the plan against remote state and require the reviewed resource/IAM scope before apply. Saved plans may contain sensitive values.

Bedrock is disabled with no model permission. GitHub deployment roles are disabled by a new default-false `enable_github_deployment` variable. This is a proposed safe manual-deployment baseline, not silently weakened OIDC protection. Source remains uncommitted; no source/image rebuild occurred.

## Exact resource inventory

| Area | Planned resources | Count |
| --- | --- | ---: |
| Frontend shell | Amplify app and `poc` branch, no Git integration or automatic build | 2 |
| Authentication | Invite-only Cognito pool, domain, public code-flow client, approvers group | 4 |
| App storage | DynamoDB on-demand audit table, PITR and deletion protection | 1 |
| Runtime IAM | Lambda service role and inline table/log policy | 2 |
| Image access | Existing ECR repository's Lambda pull policy | 1 |
| Compute | Lambda container function, live version alias, API invocation permission | 3 |
| HTTP API | API, integration, JWT authorizer, protected proxy route, public health/ready routes, stage | 7 |
| Observability | Two 14-day log groups, one fallback metric filter, three alarms | 6 |

Lambda: x86_64, 1024 MB, 29-second timeout, reserved concurrency 2, no provisioned concurrency/VPC/NAT. HTTP API rate 2 requests/sec and burst 5; authentication required for application routes. Health/readiness remain public. Alarm notifications have no SNS recipient yet; console-only monitoring is a limitation. Amplify assets are public; business data is authenticated.

No Cognito invitations, frontend artifact upload, budget mutation, new OIDC provider, GitHub deploy role, RDS, secret, managed Bedrock component or paid model test is included.

## IAM review

- `bizzybee-poc-runtime` trusts only `lambda.amazonaws.com`.
- Runtime permits `logs:CreateLogStream` and `logs:PutLogEvents` only beneath `/aws/lambda/bizzybee-poc-backend`; `dynamodb:GetItem`, `PutItem`, `UpdateItem` only on `bizzybee-poc-audit`. No payment, delete, Cognito administration, state access or Bedrock actions.
- ECR policy permits Lambda service `BatchGetImage`/`GetDownloadUrlForLayer`, conditioned on the exact backend function SourceArn.
- Lambda resource policy permits API Gateway invocation of the live alias only from the newly created API execution ARN.
- The separately approved infrastructure operator will require resource creation/read/tag permissions for these services and `iam:PassRole` limited to the new runtime role for Lambda. This plan does not grant the operator new credentials or broad administrator permissions.

## Verified account checks

STS identity verified before reads. No matching POC Lambda, audit table, HTTP API, Cognito pool/domain, Amplify app or IAM role found in the queried inventories. Existing unrelated resources remain untouched. No runtime S3 state exists. Lambda regional quota is 1000 with 1000 unreserved, leaving adequate capacity for reserved concurrency 2 while preserving AWS's required 100 unreserved executions. Recheck collisions and quota before apply.

## GitHub blocker and recommended resolution

Live organization plan: **Free**. Both repositories have only the unprotected `copilot` environment; no `poc` environment exists. GitHub's documentation limits required environment reviewers on Free/Pro/Team to public repositories. These repositories are private, so the original approval gate is unavailable. A workflow_dispatch condition alone is not an equivalent independent approval boundary.

**Recommend for this low-cost POC:** keep GitHub Actions CI, create no GitHub AWS deployment roles, and perform artifact deployments manually through the owner's approved local AWS session after each explicit release approval. Do not use stored AWS keys or make repositories public as a workaround. This defers the automated CD deliverable; enabling it requires an agreed enforceable gate or a suitable GitHub plan. No GitHub upgrade or settings change has been made.

Source: [GitHub deployment protection availability](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments), [AWS concurrency constraint](https://docs.aws.amazon.com/lambda/latest/api/API_PutFunctionConcurrency.html).

## Refreshed cost review

AWS budget read-back remains USD 1.10 actual / USD 1.299 forecast, last updated September 26 at 19:59:39 Singapore. Apparent USD 48.90 headroom is delayed, not a real-time balance. Existing workloads continue to consume it. Credits/refunds are excluded; taxes/support are included by the existing calculation. Budget alerts are not a cap.

Read Singapore OnDemand prices directly from AWS Pricing GetProducts during this review:

| Meter | USD rate |
| --- | ---: |
| Lambda x86 compute | 0.0000166667 / GB-second |
| Lambda requests | 0.20 / million |
| HTTP API requests | 1.25 / million |
| Standard DynamoDB writes / reads | 0.71 / million WRU; 0.1425 / million RRU |
| DynamoDB PITR | 0.228 / GB-month |
| ECR storage | 0.10 / GB-month |
| Standard CloudWatch log ingestion / storage | 0.70 / GB; 0.03 / GB-month |
| Standard alarm metric | 0.10 / month |
| Amplify static storage | 0.023 / GB-month |

At 10,000 monthly API calls averaging 1 GB-second, Lambda plus HTTP API is approximately USD 0.1812 before tax, data transfer and other meters. Cold starts and slower SQL increase billed duration. DynamoDB charges per item-size unit, not per application request: a 20 KB workflow write consumes 20 WRUs, and approval updates rewrite the item. Large evidence payloads or repeated decisions increase costs.

Retain **USD 13/month incremental planning allowance** from PLAN.md for four users, small transfer/log volumes, limited image retention, audit storage and contingency. It is not an exact quote: custom metric charges, paid storage tiers, tax, transfer, existing Cognito free-tier consumption and real duration still need monitoring. Bedrock spend is zero while disabled. No NAT/always-on server/GitHub subscription expense is proposed. GitHub billing is separate from the AWS budget.

Sources: [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [Cognito pricing and account-shared free tier](https://aws.amazon.com/cognito/pricing/), [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/), and live AWS regional Pricing API results. Free-tier credits were not assumed to eliminate the planning allowance.

## Decision required

Approve the **manual owner-operated deployment approach** instead of GitHub CD for this POC. After that decision, request a bounded authorization for runtime S3 initialization/locking and creation of the 26 listed resources with exactly this image and inference disabled. Regenerate/review the remote-backed plan before applying. Invitations, frontend release, budget alert changes and paid inference remain separate gates.

Acceptance after deployment: unauthenticated APIs denied, Cognito callback/PKCE login, owner-only approval, immutable evidence/conditional transitions, packaged dataset/cutoff, explicit CORS, logs and alarms, bounded latency, and alias rollback. Do not claim any of these AWS acceptance tests have run yet.
