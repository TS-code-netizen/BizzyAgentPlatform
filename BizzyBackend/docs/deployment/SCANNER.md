# Backend image scan

The former v0.67.2 installer failed before scanning; its GitHub release API returns 404. The workflow now invokes `scripts/scan_image.sh` on the exact saved image archive subsequently uploaded for deployment.

The script uses the official immutable [Trivy v0.74.0 release](https://github.com/aquasecurity/trivy/releases/tag/v0.74.0). The Linux amd64 archive SHA-256 is pinned in source and verified before extraction/execution, against the digest published in GitHub release asset metadata. No installer is fetched from a moving branch. A checksum mismatch or scanner/database failure blocks delivery.

HIGH and CRITICAL findings remain blocking, including unfixed vulnerabilities. Vulnerability and secret scanners remain enabled. Download retries and download/scan timeouts are bounded. No finding is suppressed and no application dependency or Bee implementation is changed by this repair.

To update the scanner, verify a new official immutable release, review its security advisories, update both URL and independently verified digest, and run the full image scan. Do not switch to latest or disable the gate. Upstream incident context: https://github.com/aquasecurity/trivy/discussions/10425 .

Run on Linux amd64: `bash scripts/scan_image.sh image.tar`. The workflow publishes the image artifact only after a successful scan. A scanner installation fix is not evidence that the application image is vulnerability-free; new findings require separate review before deployment.
