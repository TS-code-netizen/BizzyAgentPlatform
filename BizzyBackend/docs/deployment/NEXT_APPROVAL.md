# Next approval package

Prepared September 27, 2026 (Singapore). **A and B were explicitly approved and executed.** Final budget decision is **USD 50/month recurring, account-wide**. This supersedes the interim SGD requirement and future-month uncertainty in earlier reports. The evidence below describes the pre-execution snapshot; the execution record follows.

## Execution record

- Verified account and S3 encryption/versioning/public-access/TLS controls before migration; confirmed destination absent. Verified local backup volume has FileVault enabled. Retained mode-0600 pre/post migration backups under `/private/tmp/bizzybee-approved-release/`; this temporary directory is recovery material, not a long-term backup strategy.
- Activated bootstrap S3 backend and ran interactive `init -migrate-state`, explicitly confirming the local-to-empty-S3 copy. Remote object has AES256 encryption and a version ID. All seven resource records and outputs exactly match the retained original state. Subsequent bootstrap plan returned exit 0 with **no changes**; native locking was enabled.
- Verification caveat: Terraform 1.15.3 migration produced a new lineage and serial 1 versus the original serial 8. The strict metadata-equality check failed; resource/output equality and the clean refreshed plan independently passed. Both snapshots were retained; no state was force-pushed or overwritten to hide the mismatch. The S3 state is now the configured authority. Do not restore the older local lineage over it; investigate metadata semantics before any recovery operation.
- Published the exact approved local image without rebuilding, under immutable tag `poc-bootstrap-77b77290b571`. The initial isolated Docker credential config lacked the Desktop context; retry used the discovered explicit Docker endpoint. Temporary registry credential files were removed after each attempt.
- ECR manifest digest: `sha256:5946da98660a6301944182d010efd2e350637e758a087b83d6c82c4373718d09` in `524097108092.dkr.ecr.ap-southeast-1.amazonaws.com/bizzybee-poc-backend`.
- Automatic ECR scan completed September 27 at 01:10:50 Singapore with an empty reported severity-count map: no HIGH/CRITICAL findings reported. This is scanner coverage at that time, not a guarantee of absence of vulnerabilities; earlier container/Python Trivy validation remains separate evidence.
- Private provenance and scan summaries: `/private/tmp/bizzybee-approved-release/provenance.json` and `ecr-scan.json`. Source hashes are a current working-tree snapshot, not proof of a clean committed release. No Git commit or push was performed.
- No application deployment, IAM change, invitation, budget update, GitHub setting change or paid inference occurred. Runtime planning/apply remains a subsequent gate.

## Refreshed evidence

- STS verified account `524097108092` before account reads.
- Existing budget: USD 50 MONTHLY, UnblendedCost excluding Credit/Refund. Actual USD 1.10, forecast USD 1.299, still last updated September 26 at 19:59:39 Singapore. These are delayed snapshots, not real-time spend.
- Cost Explorer, September 1 through September 25 inclusive: USD 1.0938081791, estimated, same Credit/Refund exclusion. The queried UTC day boundary was September 26.
- Existing notifications: actual >85%, >100%, forecast >100%. Proposed >50/80/100 actual and >100 forecast remain unapplied.
- State bucket currently has zero objects; ECR has zero images. Bootstrap state remains local and must be preserved.
- Inspected local image `bizzybee-poc-validation:local`: linux/amd64, 673792017 bytes, image ID `sha256:77b77290b57166297c46a595f5a03556142a285e744f12e291dbadc40c19191e`. This is a local image identifier, NOT an ECR manifest digest. Prior tests/scan are recorded in COMPLETION.md; recheck image identity before push and do not rebuild silently.

## Approval A: migrate bootstrap state

Destination: `s3://bizzybee-poc-tfstate-524097108092/bootstrap/terraform.tfstate`, Singapore. Native S3 lock object: `bootstrap/terraform.tfstate.tflock`. No new resource or IAM policy creation is requested.

After explicit approval:

1. Reverify STS account, bucket encryption/versioning/public-access/TLS controls, local state lineage/serial and exactly seven managed resources. Check destination is still absent; stop on any collision.
2. Preserve a mode-0600 local backup on encrypted storage; never print state or upload it as a build artifact. Stop if safe backup storage is unavailable.
3. Add `backend "s3" {}` inside bootstrap's Terraform block. Use the prepared `infra/bootstrap/backend.hcl.example`; it is not active configuration yet.
4. Run `terraform -chdir=infra/bootstrap init -migrate-state -backend-config=backend.hcl.example` interactively. Review and confirm the intended local-to-S3 migration; do not use force-copy or reconfigure to bypass checks.
5. Verify remote object encryption/version and state lineage/serial/resource IDs against the retained local copy without displaying sensitive contents. Run a normal bootstrap plan and require zero changes. Retain local recovery material until verification succeeds.

Minimum existing identity permissions: bucket ListBucket for this prefix; GetObject/PutObject for the state key; GetObject/PutObject/DeleteObject only for the lock key, plus read access for verification. No DeleteObject permission is needed for state. No credential belongs in HCL. Native locking/versioning guidance: [HashiCorp S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3).

Failure recovery: stop applies, preserve both state copies and lock diagnostics, establish which state is authoritative by lineage/serial. Never force-unlock an active operation or overwrite a remote state with an older local copy.

## Approval B: publish only the tested container

Repository: `524097108092.dkr.ecr.ap-southeast-1.amazonaws.com/bizzybee-poc-backend`. Proposed immutable tag: `poc-bootstrap-77b77290b571`. This is an explicitly dirty working-tree bootstrap artifact, not a committed Git release; do not label it with the base Git SHA as if it represented committed source.

After explicit approval, revalidate the exact local image ID above, record source/dataset provenance and validation evidence, ensure the tag is absent, authenticate using a temporary Docker config and an ECR password pipe, tag that exact image and push it without rebuilding. Never print or persist the registry token in repository files. Retrieve the registry manifest digest, wait for scan completion with a bounded timeout and reject HIGH/CRITICAL findings before runtime planning. Record image digest and scan result in private release evidence. A digest must come from ECR, not the local image ID.

Minimum permissions: ecr:GetAuthorizationToken on `*`; InitiateLayerUpload, UploadLayerPart, CompleteLayerUpload, BatchCheckLayerAvailability, PutImage, DescribeImages and DescribeImageScanFindings on this repository. No Lambda update, role passing or runtime IAM changes. Storage/scan costs apply; this does not start the application. Retain the tagged image if publication succeeds; deletion is not included in approval.

## Subsequent review, not covered by A/B

- Use the verified ECR digest to prepare the real runtime Terraform plan and exact IAM/resource inventory. No fabricated digest or claim of a completed runtime plan.
- Refresh unit prices, monthly estimate and delayed account spend before runtime approval. Current USD 13/month planning allowance is not a complete price quote or spending cap.
- State initialization/locking for runtime and budget, budget import/notification changes, GitHub settings, infrastructure apply, Cognito invitations and paid Bedrock testing require their own explicit scope. Bedrock remains disabled.
- Stop before enabling OIDC deployment roles if protected private-repository deployment environments cannot enforce trusted refs and the agreed approval boundary.

A and B are complete. Neither authorization includes application deployment or budget notification changes.
