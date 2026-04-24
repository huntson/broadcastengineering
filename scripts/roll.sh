#!/usr/bin/env bash
# Roll a master/spoke subproject to a specific (or the latest) published
# image tag.
#
# Usage:
#   scripts/roll.sh <subproject>            # roll to the latest published tag
#   scripts/roll.sh <subproject> v0.2.1     # pin to a specific version
#   scripts/roll.sh --list <subproject>     # show available versions, no changes
#
# Behavior:
#   - Queries the master repo's tags via `git ls-remote` (no clone needed).
#   - Updates every `image: registry.broadcastglue.com/<subproject>:vX.Y.Z`
#     line in any compose file in this spoke.
#   - Commits with `<subproject>: chore: roll to vX.Y.Z` and pushes.
#   - Exits 0 cleanly if no compose file in this spoke references the
#     subproject (so this script is safe to ship to every spoke).
#   - Does NOT touch Portainer. After a successful run, click "Update the
#     stack" in Portainer to pull and restart with the new image.

set -euo pipefail

MASTER_URL="https://github.com/huntson/broadcastglue.git"
REGISTRY_PREFIX="registry.broadcastglue.com"

usage() {
    cat >&2 <<EOF
Usage: $0 <subproject> [version]
       $0 --list <subproject>

Examples:
  $0 supervisor             # roll to latest published version
  $0 supervisor v0.2.1      # pin to a specific version
  $0 --list supervisor      # show available versions
EOF
    exit 2
}

list_mode=0
if [ "${1:-}" = "--list" ]; then
    list_mode=1
    shift
fi

SUBPROJECT="${1:-}"
PINNED_VERSION="${2:-}"

[ -z "$SUBPROJECT" ] && usage

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    printf 'error: not in a git repo.\n' >&2
    exit 1
fi
cd "$REPO_ROOT"

remote_tags=$(git ls-remote --tags --refs "$MASTER_URL" "${SUBPROJECT}/v*" 2>/dev/null \
    | awk '{print $2}' \
    | sed "s|refs/tags/${SUBPROJECT}/||" \
    | sort -V)

if [ -z "$remote_tags" ]; then
    printf 'No tags matching %s/v* found in master (%s).\n' "$SUBPROJECT" "$MASTER_URL" >&2
    exit 1
fi

if [ "$list_mode" -eq 1 ]; then
    printf 'Available %s versions in master:\n' "$SUBPROJECT"
    printf '%s\n' "$remote_tags"
    exit 0
fi

LATEST="$(printf '%s\n' "$remote_tags" | tail -n1)"

if [ -z "$PINNED_VERSION" ]; then
    TARGET="$LATEST"
else
    TARGET="$PINNED_VERSION"
    case "$TARGET" in v*) ;; *) TARGET="v$TARGET" ;; esac
    if ! printf '%s\n' "$remote_tags" | grep -qx "$TARGET"; then
        printf 'error: %s is not a published version of %s.\n' "$TARGET" "$SUBPROJECT" >&2
        printf 'available:\n%s\n' "$remote_tags" >&2
        exit 1
    fi
fi

# Find compose files in this spoke that reference this subproject's image.
COMPOSE_FILES=()
while IFS= read -r f; do
    [ -n "$f" ] && COMPOSE_FILES+=("$f")
done < <(grep -rlE "^[[:space:]]*image:[[:space:]]+${REGISTRY_PREFIX}/${SUBPROJECT}:" \
            --include='*.yml' --include='*.yaml' . 2>/dev/null || true)

if [ "${#COMPOSE_FILES[@]}" -eq 0 ]; then
    printf 'No compose files in this spoke reference %s/%s. Nothing to roll.\n' \
        "$REGISTRY_PREFIX" "$SUBPROJECT"
    exit 0
fi

CHANGED=()
for f in "${COMPOSE_FILES[@]}"; do
    # Already at target on every line in this file? skip.
    other_versions=$(grep -E "^[[:space:]]*image:[[:space:]]+${REGISTRY_PREFIX}/${SUBPROJECT}:" "$f" \
                       | grep -vE ":${TARGET}([[:space:]]|$)" || true)
    if [ -z "$other_versions" ]; then
        continue
    fi
    # In-place replace of any version-pinned image line for this subproject.
    sed -i.bak -E "s|^([[:space:]]*image:[[:space:]]+${REGISTRY_PREFIX}/${SUBPROJECT}):[A-Za-z0-9._-]+|\1:${TARGET}|" "$f"
    rm -f "${f}.bak"
    CHANGED+=("$f")
    printf 'updated %s\n' "$f"
done

if [ "${#CHANGED[@]}" -eq 0 ]; then
    printf 'Already at %s in every compose file. Nothing to do.\n' "$TARGET"
    exit 0
fi

git add -- "${CHANGED[@]}"
git commit -m "${SUBPROJECT}: chore: roll to ${TARGET}" --quiet

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push --quiet origin "${BRANCH}"

printf '\n%s rolled to %s.\nNext: click "Update the stack" in Portainer to pull and restart.\n' \
    "$SUBPROJECT" "$TARGET"
