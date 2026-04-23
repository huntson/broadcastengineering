# Versioning

This repo is a monorepo of ~30 independently-released subprojects. Each has
its own semver version and its own tag namespace.

## TL;DR

- Each subproject has a `VERSION` file at its root (e.g. `fs_mon/VERSION`).
- Tags are namespaced: `<subproject>/vMAJOR.MINOR.PATCH` (e.g. `fs_mon/v1.0.1`).
- Commits follow **Conventional Commits**. The type in the subject determines
  the version bump.
- After making commits to a subproject, run `scripts/release.sh <subproject>`.
  It reads commits since the last tag, computes the bump, writes `VERSION`,
  commits, tags, and pushes. No human decision required.

## Commit format

```
<subproject>: <type>[(<scope>)][!]: <short description>

[optional body]
[optional: BREAKING CHANGE: description]
```

The `<subproject>:` prefix is optional — path-filtering in `release.sh` is
what ties commits to subprojects. The prefix is just a readability aid that
matches the repo's existing commit style.

**Types:**

| Type | Meaning | Bump (stable ≥1.0) | Bump (pre-stable 0.x) |
|---|---|---|---|
| `feat`     | New feature | MINOR | MINOR |
| `fix`      | Bug fix | PATCH | PATCH |
| `perf`     | Performance improvement | PATCH | PATCH |
| `refactor` | Code refactor, no behavior change | none | none |
| `docs`     | Documentation only | none | none |
| `chore`    | Tooling, deps, misc | none | none |
| `test`     | Test-only changes | none | none |
| `build`    | Build system / Dockerfile | none | none |
| `ci`       | CI config | none | none |

**Breaking changes:** either append `!` after the type (`feat!:`) or include
`BREAKING CHANGE: <desc>` in the body. In stable (≥1.0) this bumps MAJOR;
in pre-stable (0.x) it bumps MINOR (per semver §4).

**Examples:**

```
fs_mon: feat: priority polling for immediate UI updates
fs_mon: fix: wake polling threads immediately via threading.Event
fs_mon: feat!: rename config key poll_interval → poll_interval_ms

BREAKING CHANGE: existing configs with poll_interval must be updated.
```

## Tag format

`<subproject>/vX.Y.Z`. Find the latest tag for a subproject with:

```sh
git describe --tags --match "fs_mon/v*" --abbrev=0
```

## Release script

Two modes:

```sh
scripts/release.sh <subproject>   # monorepo mode: VERSION at <subproject>/VERSION,
                                  # tags <slug>/vX.Y.Z  (slug = lowercased,
                                  # spaces→'-')
scripts/release.sh .              # single-project mode: VERSION at repo root,
                                  # tags vX.Y.Z
```

Full cycle:

1. `git fetch --tags` to avoid stale state.
2. Finds the latest applicable tag (`<slug>/v*` or `v*`).
3. Reads commits since that tag (path-filtered to `<subproject>/` in monorepo
   mode; whole repo in single-project mode).
4. Classifies each commit by its conventional type. Picks the highest bump
   (`major` > `minor` > `patch` > `none`).
5. If bump is `none` (only chore/docs/refactor/test/build/ci): exits silently.
   No tag.
6. Otherwise: bumps `VERSION`, commits `chore(release): vX.Y.Z` (with
   `<subproject>:` prefix in monorepo mode), tags, pushes both the branch and
   the tag to `origin`.

## Deploy vs. release — what goes in `/api/health`

`VERSION` is the last *released* version. To identify *what is actually
running*, expose both in health endpoints / bundle manifests:

```json
{"version": "1.0.1", "commit": "733c558"}
```

Build the commit SHA in via:

```dockerfile
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}
```

```sh
docker compose build --build-arg GIT_SHA=$(git rev-parse --short HEAD)
```

Test deploys do NOT get tags. The SHA tells you what's on the host; the
version tells you the last official release.

## When a session should release

After making commits to one or more subprojects, a Claude session should run
`scripts/release.sh <subproject>` for each one before ending. The script is
idempotent and a no-op when no releasable commits exist, so running it
defensively is safe.

If two concurrent sessions race on the same subproject, the second one's
`git push` will fail on the tag reference. Fetch, rebase, re-run the script.

## Starting versions

Chosen 2026-04-23 via a one-time audit of commit history. See the initial
release commit for rationale. From that point forward, version progression
is mechanical.
