# Prepared pull request descriptions

These are drafts only; no branches, commits or PRs have been created. Inspect concurrent frontend PR #4 before publishing a frontend PR. Do not pop backup stashes or commit directly to main.

## BizzyBackend

Title: Prepare approval-gated AWS POC delivery and deterministic security controls

Summary: Replace the implicit OpenAI fallback with opt-in Bedrock Converse routing; implement Cognito signed identity, owner-only conditional approvals and DynamoDB evidence persistence; fail closed on unrecognized/RED action types; package verified dataset provenance and Lambda runtime; add Terraform bootstrap/runtime/account-budget roots and OIDC delivery pipeline. Maintain one logical FastAPI service and deterministic calculations.

Validation: 94 tests passed on local Python 3.11 and container Python 3.12; 40 existing opt-in routing tests skipped. Lambda image/data smoke passed under 1 GB/read-only root; HIGH/CRITICAL image scan passes after patched dependency updates. Terraform roots validate; actionlint passes; bootstrap plan is seven additions with no changes/deletions.

Compatibility: Deployed APIs now require Cognito access tokens. Query user is ignored in favor of signed identity. Audit visibility is owner-or-creator. Unknown GREEN action names now fail closed. Production configuration requires Cognito/table/HTTPS origins. FastAPI/Starlette/PyJWT updated to address security findings; no real payment or external action execution is introduced.

Deployment: Not deployed. Read docs/deployment/PLAN.md and COMPLETION.md. Runtime rollout depends on approved bootstrap, tested ECR image and environment protections. All external changes require explicit review/approval.

## BizzyFrontend

Title: Add invite-only Cognito login and owner draft-decision controls

Summary: Add pinned oidc-client-ts PKCE login, memory-only sessions, authenticated API requests with deadlines, owner-only approve/reject controls and server identity semantics. Add reviewed backend contract snapshot/checks and manual Actions-controlled Amplify delivery of a tested zip. No secrets in public build variables.

Validation: npm ci/lint/build/contract checks passed; existing local frontend/backend integration passed. Authenticated Cognito browser flow remains a post-provisioning acceptance test. No remote deployment performed.

Compatibility: Production needs all documented VITE_COGNITO_* and API variables. Refresh requires Cognito sign-in again because tokens are not persisted. Existing five-language UI does not imply five-language localized backend responses. Coordinate with the open dashboard PR rather than superseding it.

## BizzyData

Title: Validate reproducibility and publish checksummed dataset artifacts in CI

Summary: Add a read-only validation gate, isolated CI regeneration comparison, deterministic versioned archive/manifest packaging and SHA-pinned artifact workflow. No CSV content/schema change; no private cross-repository credentials.

Validation: Current validator passes all 21 CSVs/498535 rows/scenarios; regeneration in a temporary copy compares byte-for-byte with source. Workflow actionlint passes. Packaging records commit and SHA-256 provenance.

Shared operational documentation: BizzyBackend/docs/deployment/PLAN.md. AWS account budget and infrastructure do not belong to this repository.
