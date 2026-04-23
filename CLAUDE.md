# Repo instructions for Claude

This is a monorepo of ~30 Dockerized services, each versioned independently.

## Commit format — REQUIRED

Every commit must follow Conventional Commits. A `commit-msg` hook enforces
this (`.githooks/commit-msg`). Subjects must match one of:

```
<type>[(scope)][!]: <description>
<subproject>: <type>[(scope)][!]: <description>
```

Valid types: `feat` `fix` `perf` `refactor` `docs` `chore` `test` `build`
`ci` `style` `revert`. Append `!` or put `BREAKING CHANGE:` in the body for
breaking changes.

Prefer the `<subproject>:` prefix — it matches the repo's existing style.
Use the top-level form only for commits that don't belong to a single
subproject (tooling, repo-wide docs).

**Choose the type accurately.** `scripts/release.sh` parses the type to
decide the version bump:

| Type | Bump (stable ≥1.0) | Bump (pre-stable 0.x) |
|---|---|---|
| `feat`        | MINOR | MINOR |
| `fix`, `perf` | PATCH | PATCH |
| `!` / `BREAKING CHANGE:` | MAJOR | MINOR |
| everything else | none  | none  |

## Releasing — REQUIRED after making commits

Before ending a session that committed changes, run `scripts/release.sh`
with the appropriate scope:

```sh
scripts/release.sh <subproject>   # monorepo: for each subproject touched
scripts/release.sh .              # single-project repo: once, at the end
```

The script is idempotent: it's a no-op when there are no releasable commits
(only chore/docs/refactor/test/build/ci). When there are, it bumps `VERSION`,
commits, tags, and pushes.

Run it even if you're unsure — it will silently do nothing if there's
nothing to release.

## Tag format

`<subproject>/vMAJOR.MINOR.PATCH`. Find the latest for a subproject with:

```sh
git describe --tags --match "<subproject>/v*" --abbrev=0
```

## Full protocol

See `VERSIONING.md`.

## First-time setup in a fresh clone

```sh
scripts/install-hooks.sh
```

This sets `core.hooksPath=.githooks` so the commit-msg hook is active.
