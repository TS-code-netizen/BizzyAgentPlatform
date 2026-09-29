#!/usr/bin/env bash
set -euo pipefail

archive="${1:?Usage: scan_image.sh IMAGE_ARCHIVE}"
test -f "$archive"
scanner_dir="$(mktemp -d)"
trap 'rm -rf "$scanner_dir"' EXIT
curl --fail --show-error --location --retry 3 --connect-timeout 10 --max-time 180 \
  https://github.com/aquasecurity/trivy/releases/download/v0.74.0/trivy_0.74.0_Linux-64bit.tar.gz \
  --output "$scanner_dir/trivy.tar.gz"
printf '%s  %s\n' '2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a' "$scanner_dir/trivy.tar.gz" | sha256sum --check --strict
tar -xzf "$scanner_dir/trivy.tar.gz" -C "$scanner_dir" trivy
"$scanner_dir/trivy" --version
"$scanner_dir/trivy" image --input "$archive" --scanners vuln,secret \
  --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed=false --format table --timeout 10m
