# Repo instructions for Claude

## This repo

**broadcastengineering** — a monorepo of 4 broadcast-engineering subprojects:
`fs-emu`, `gv-surface-datetime-fix`, `k-frame status`, `k-frame-quartz-bridge`.
Mix of scripts and Windows EXE apps.

**Mode:** monorepo. Each subproject has its own `VERSION` file and its own
tag namespace (`<subproject>/vX.Y.Z`). Note `k-frame status` has a space
in its directory name; `release.sh` slugs it to `k-frame-status` for tags
(git refs can't contain spaces).

**Release command** (run before ending a session that made commits):
```sh
scripts/release.sh <subproject>     # for EACH subproject you touched
```

The script is idempotent — silent no-op when nothing releasable.

## ⚠️ Tag-triggered GitHub Actions

Pushing the tag `k-frame-quartz-bridge/vX.Y.Z` triggers a Windows EXE
build (`.github/workflows/build-k-frame-quartz-bridge.yml`, ~5 min). The
workflow reads `VERSION` from git, builds `k-frame-quartz-bridge.exe`, and
attaches it to the GitHub Release created by the tag. **Don't push
throwaway/test tags for this subproject** — every pushed tag publishes a
customer-visible release.

Historical hyphen-convention tags (`k-frame-quartz-bridge-v1.0.1` …
`-v1.0.5`, `v1.0.1` … `v1.0.23`, `-latest`) exist as archaeological
evidence from before the protocol rollout. No new ones are created.

## Commit format — REQUIRED (enforced by .githooks/commit-msg)

```
<subproject>: <type>[(scope)][!]: <description>
```

Or, for repo-wide changes:
```
<type>[(scope)][!]: <description>
```

Valid types: `feat` `fix` `perf` `refactor` `docs` `chore` `test` `build`
`ci` `style` `revert`. Append `!` or include `BREAKING CHANGE: ...` in the
body for breaking changes.

**Choose the type accurately.** `scripts/release.sh` parses the type to
decide the version bump:

| Type | Bump (stable ≥1.0) | Bump (pre-stable 0.x) |
|---|---|---|
| `feat`                   | MINOR | MINOR |
| `fix`, `perf`            | PATCH | PATCH |
| `!` / `BREAKING CHANGE:` | MAJOR | MINOR |
| everything else          | none  | none  |

## Tag format

`<slug>/vMAJOR.MINOR.PATCH`, where slug is the subproject directory
name lowercased with spaces replaced by `-`.

## Full protocol

See `VERSIONING.md`.

## First-time setup in a fresh clone

```sh
scripts/install-hooks.sh
```

This sets `core.hooksPath=.githooks` so the commit-msg hook is active.
