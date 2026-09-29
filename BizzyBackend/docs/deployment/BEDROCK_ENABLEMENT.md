# Bedrock enablement approval package

**Execution update:** the user approved this package. Both Terraform updates were applied, candidate version 2 passed readiness, and live was conditionally promoted from 1 to 2. See RUNTIME_STATUS.md for current verification and remaining runtime-inference acceptance. The preparation notes below are historical.

Prepared after the single approved operator smoke passed. No enablement has been applied. Live alias is version 1 with provider disabled. Account 524097108092, Singapore; monthly account-wide budget remains USD 50.

## Verified review plan

`/private/tmp/bizzybee-bedrock-enable-review.tfplan`: **0 additions, 2 in-place updates, 0 deletions**. Generated read-only with locking disabled; regenerate with locking and compare before an approved apply. Source inputs are infra/runtime/terraform.tfvars.example, the published image digest, and enable_inference=true. GitHub deployment remains disabled. Do not apply default variables later without retaining the approved model inputs: defaults intentionally disable inference.

1. Add only `bedrock:InvokeModel` to the existing runtime inline policy, scoped to the exact Nova Micro APAC inference profile in account 524097108092 and its six destination foundation-model ARNs listed in terraform.tfvars.example. No wildcard models, streaming, model activation, Marketplace, IAM administration or third-party keys.
2. Set Lambda `BIZZY_MODEL_PROVIDER=bedrock` and `BEDROCK_MODEL_ID=apac.amazon.nova-micro-v1:0`, publishing a new immutable function version. Keep the same container digest, memory/concurrency limits, authorization, deterministic calculations and approval controls. Output limit remains 128 tokens, transport timeout 6 seconds, one total SDK attempt.

The profile destinations were read again and remain Singapore, Sydney, Tokyo, Seoul, Osaka and Mumbai. No automatic provider/model/geography fallback is authorized. A future destination change requires renewed review.

## Alias promotion is a separate step within requested approval

Terraform deliberately ignores live alias version drift because releases own promotion. The two-update plan alone will NOT enable the live application. After apply, read the newly published version, verify its image/environment and ready endpoint, then conditionally promote `live` using its current RevisionId. Do not assume the new version number or overwrite a concurrent promotion. Record old/new version and revision evidence.

Readiness does not invoke Bedrock. After promotion the invited users' questions may incur inference charges when deterministic routing cannot handle them. Operator smoke success does not prove runtime-role invocation. Confirm runtime access through an authenticated user question and structured outcome/token/latency logs; do not impersonate a user or replay HAR credentials. No extra synthetic paid requests are included in this proposal.

## Rollback and limits

If readiness fails, do not promote. If live acceptance fails, conditionally restore the recorded previous live version 1 using a fresh RevisionId. This disables inference for traffic immediately through its old immutable environment, but leaves the new version and runtime permission present. Removing the Bedrock policy/config requires a reviewed follow-up plan, not destructive version deletion.

The previous single test used 74 input and 7 output tokens in 507 ms. This is not a throughput or multilingual quality assessment. Charges remain usage-based; USD 50 is an alert budget, not a cap. No frontend rebuild, budget notification change, invitation, GitHub change or image push is included. Public frontend release metadata currently records provider disabled; it describes its build-time snapshot and must not be treated as live backend configuration after promotion.

## Requested approval

Approve the two exact Terraform updates and subsequent conditional live-alias promotion, allowing model inference for normal invited-user application traffic. Keep all deterministic authorization/approval restrictions. No changes are made until this scope is explicitly approved.
