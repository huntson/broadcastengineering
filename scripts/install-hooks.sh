#!/usr/bin/env bash
# Point git at the repo's checked-in hooks.
# Run once per clone. Idempotent.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true

printf 'hooks installed: core.hooksPath=.githooks\n'
