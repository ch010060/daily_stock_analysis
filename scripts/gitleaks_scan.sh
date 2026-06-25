#!/usr/bin/env bash
# Run gitleaks against this repo's git history with .gitleaksignore honored
# regardless of the directory you invoke this script from.
#
# gitleaks' --gitleaks-ignore-path and --source both default to "." (the
# current working directory), not the git root, so running `gitleaks detect`
# from a subdirectory (e.g. apps/dsa-web) silently misses .gitleaksignore and
# re-reports already-triaged false positives. This wrapper pins both to the
# repo root so the result is the same no matter where it's invoked from.
#
# Usage: scripts/gitleaks_scan.sh [gitleaks detect flags...]
# Example: scripts/gitleaks_scan.sh --log-opts="<base>..HEAD"

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

exec gitleaks detect \
  --redact \
  --source "$repo_root" \
  --gitleaks-ignore-path "$repo_root" \
  "$@"
