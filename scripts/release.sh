#!/usr/bin/env bash
# Compute and apply the next semver release.
#
# Modes:
#   scripts/release.sh <subproject>   # VERSION at <subproject>/VERSION,
#                                     # tags <slug>/vX.Y.Z  (slug = subproject
#                                     # with spaces→'-', lowercased).
#   scripts/release.sh .              # Whole-repo release:
#                                     # VERSION at ./VERSION, tags vX.Y.Z.
#
# Reads Conventional Commit types since the last applicable tag, picks the
# highest bump (major > minor > patch > none), writes VERSION, commits, tags,
# pushes. Exits 0 silently when there are no releasable commits.
#
# See VERSIONING.md for the full protocol.

set -euo pipefail

if [ $# -ne 1 ]; then
  printf 'Usage: %s <subproject|.>\n' "$0" >&2
  exit 2
fi

SCOPE="$1"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ "$SCOPE" = "." ]; then
  VERSION_FILE="VERSION"
  TAG_PREFIX=""           # tag = vX.Y.Z
  LOG_PATH_ARGS=()        # whole repo
  COMMIT_SCOPE_LABEL=""
else
  if [ ! -d "$SCOPE" ]; then
    printf 'error: directory %q does not exist\n' "$SCOPE" >&2
    exit 2
  fi
  # Slug for tags: lowercase, spaces → '-'.
  SLUG="$(printf '%s' "$SCOPE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
  VERSION_FILE="${SCOPE}/VERSION"
  TAG_PREFIX="${SLUG}/"    # tag = <slug>/vX.Y.Z
  LOG_PATH_ARGS=(-- "${SCOPE}/")
  COMMIT_SCOPE_LABEL="${SCOPE}: "
fi

if [ ! -f "$VERSION_FILE" ]; then
  printf 'error: %s missing. Initialize it (e.g. 0.1.0) first.\n' "$VERSION_FILE" >&2
  exit 2
fi

if ! git diff --quiet -- "$VERSION_FILE"; then
  printf 'error: %s has uncommitted changes; stash or commit first.\n' "$VERSION_FILE" >&2
  exit 1
fi

git fetch --tags --quiet origin || true

LAST_TAG="$(git tag --list "${TAG_PREFIX}v*" --sort=-v:refname | head -n1 || true)"

if [ -n "$LAST_TAG" ]; then
  RANGE="${LAST_TAG}..HEAD"
else
  RANGE="HEAD"
fi

SHAS="$(git log --format='%H' "$RANGE" "${LOG_PATH_ARGS[@]}" 2>/dev/null || true)"

if [ -z "$SHAS" ]; then
  exit 0
fi

BUMP="none"  # none < patch < minor < major

escalate() {
  case "$1" in
    major) BUMP="major" ;;
    minor) [ "$BUMP" != "major" ] && BUMP="minor" ;;
    patch) [ "$BUMP" = "none" ] && BUMP="patch" ;;
  esac
}

while IFS= read -r sha; do
  [ -z "$sha" ] && continue
  subject="$(git log -1 --format='%s' "$sha")"
  body="$(git log -1 --format='%b' "$sha")"

  # Strip optional "<scope>: " prefix (case-insensitive-ish not needed; exact).
  if [ "$SCOPE" != "." ]; then
    stripped="${subject#${SCOPE}: }"
  else
    stripped="$subject"
  fi

  # Regex held in a variable for bash 3.2 compat — 3.2's [[ =~ ]] parser
  # chokes on inline patterns that contain optional grouped parens.
  _re_conv='^([a-z]+)(\([^)]+\))?(!?):'
  if [[ "$stripped" =~ $_re_conv ]]; then
    ctype="${BASH_REMATCH[1]}"
    bang="${BASH_REMATCH[3]}"
  else
    continue
  fi

  if [ "$bang" = "!" ] || grep -q '^BREAKING CHANGE:' <<<"$body"; then
    escalate "major"
    continue
  fi

  case "$ctype" in
    feat)      escalate "minor" ;;
    fix|perf)  escalate "patch" ;;
    *)         : ;;
  esac
done <<< "$SHAS"

if [ "$BUMP" = "none" ]; then
  exit 0
fi

CURRENT="$(tr -d '[:space:]' < "$VERSION_FILE")"
if ! [[ "$CURRENT" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  printf 'error: %s is not semver: %q\n' "$VERSION_FILE" "$CURRENT" >&2
  exit 1
fi
MAJ="${BASH_REMATCH[1]}"
MIN="${BASH_REMATCH[2]}"
PAT="${BASH_REMATCH[3]}"

# Pre-stable (0.x.y): MAJOR becomes MINOR per semver §4.
if [ "$MAJ" = "0" ] && [ "$BUMP" = "major" ]; then
  BUMP="minor"
fi

case "$BUMP" in
  major) MAJ=$((MAJ + 1)); MIN=0; PAT=0 ;;
  minor) MIN=$((MIN + 1)); PAT=0 ;;
  patch) PAT=$((PAT + 1)) ;;
esac

NEW_VERSION="${MAJ}.${MIN}.${PAT}"
NEW_TAG="${TAG_PREFIX}v${NEW_VERSION}"

if git rev-parse -q --verify "refs/tags/${NEW_TAG}" >/dev/null; then
  printf 'error: tag %s already exists locally. Fetch and retry.\n' "$NEW_TAG" >&2
  exit 1
fi

printf '%s\n' "$NEW_VERSION" > "$VERSION_FILE"
git add -- "$VERSION_FILE"
git commit -m "${COMMIT_SCOPE_LABEL}chore(release): v${NEW_VERSION}" --quiet
git tag -a "${NEW_TAG}" -m "${SCOPE} v${NEW_VERSION}"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push --quiet origin "${BRANCH}" "${NEW_TAG}"

printf '%s\n' "$NEW_TAG"
