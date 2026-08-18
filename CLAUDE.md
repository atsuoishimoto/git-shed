# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`git-shed` is a Python CLI (installed as `git-shed` on PATH, so Git dispatches
`git shed` to it) that links per-remote storage directories ("sheds", stored at
`~/.shed/<name>`) into a repository as `.shed/<name>`. It never manages the
contents of a shed — only the links. The README is the authoritative
description of user-visible behavior; `.plan/PLAN.md` is the original design
document (in Japanese) and may lag behind the implementation.

## Commands

```bash
# Test suite on every supported interpreter (3.11–3.14), as CI runs it
uvx uv-matrix run --max-jobs 4
uvx uv-matrix run --filter python-version=3.13    # one interpreter
uvx uv-matrix run -- tests/test_cli.py            # posargs go to pytest

# Faster during development: single interpreter, plain pytest
uv run --extra dev pytest
uv run --extra dev pytest tests/test_cli.py::test_sync_is_idempotent

# Lint and formatting (CI enforces both)
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
uv run --extra dev ruff format src tests          # apply formatting
```

CI (`.github/workflows/ci.yml`) runs exactly the matrix + ruff commands above
on Ubuntu. The tests create real Git repositories with `subprocess`, so a
usable `git` with `user.name`, `user.email` and `init.defaultBranch` configured
is assumed (CI sets these globally).

## Architecture

Everything follows one pipeline, and the module layout mirrors it:

```
discover repository (repository.py)
  → canonicalize remote URLs into identities (identity.py)
  → match identities against configured sheds (matcher.py, config.py)
  → sync .shed/ links to the matching sheds (sync.py, mount.py, links.py, exclude.py)
```

- `cli.py` — argparse subcommands (`sync`, `add`, `link`, `unlink`, `remove`,
  `status`, `list`, `path`, `open`), all reporting/printing, and the
  interactive shed-creation flow. Commands are `cmd_*` functions returning an
  exit code; every module below is UI-free and raises instead of printing.
- `repository.py` — `discover()` runs `git rev-parse` / `git remote`; every
  remote contributes an identity (`shed.remote` git config narrows this),
  uninterpretable remotes become warnings on the `Repository` object, and a
  repository with no usable remote falls back to its directory name.
- `identity.py` — `canonicalize()` turns any remote URL form (scp-style, ssh,
  https, file, local path) into `host/path` with protocol/user/`.git` stripped.
- `matcher.py` — segment-wise pattern matching, case-insensitive; `*` is one
  segment, `**` zero or more. Multiple sheds may match; there is no priority.
- `config.py` — the `Shed`/`Config` dataclasses, `~/.config/git-shed/config.toml`
  read **and** written through `tomlkit` so user comments and formatting
  survive edits; also `shed_path()` / `storage_root()` (`GIT_SHED_ROOT`
  override) and `validate_name()` (Windows-safe name rules).
- `sync.py` — pure logic producing a `SyncResult` (added/removed/relinked/
  blocked/skipped); `cli.py` renders it.
- `mount.py` — the only OS-specific code: symlinks on Unix, directory
  junctions (`mklink /J`) on Windows, behind `mount`/`unmount`/`is_mount`.
- `links.py` — `.shed/.sheds`, the list of explicitly linked sheds
  (`git shed link`) that `sync` must not drop.
- `exclude.py` — appends `/.shed/` to `.git/info/exclude`.
- `errors.py` — `GitShedError` hierarchy; `main()` catches it, prints
  `git shed: <message>` to stderr and exits 1. Warnings print as
  `git shed: warning: ...` on stderr. Exit 0 includes "nothing matched".

## Invariants to preserve

These are the product's safety guarantees; tests enforce them and changes must
not weaken them:

- **Never delete shed data.** Only links/junctions may be removed, ever
  (`mount.unmount` refuses non-links). `remove` drops definitions, not data.
- A real file or directory inside `.shed/` is left alone with a warning
  (`blocked`/`skipped` in `SyncResult`), never replaced or deleted.
- Only `.git/info/exclude` is modified — never `.gitignore`.
- Config-file edits go through tomlkit document editing (never re-serialize
  from the dataclasses) so user formatting and comments are preserved.

## Conventions

- Python 3.11+ (`from __future__ import annotations` in every module), frozen
  dataclasses for value types, `pathlib` throughout. `tomlkit` is the only
  runtime dependency; keep it that way.
- Ruff is both linter (rules `E,F,W,I,UP,B,SIM,RUF`) and formatter.
- Internal vocabulary: an *identity* is a canonicalized remote
  (`github.com/acme/foo`), the *mountpoint* is `repo/.shed/`, and a *mount* is
  one link inside it. `MOUNTPOINT` lives in `repository.py`.
- Tests live in `tests/` and run against the real filesystem and real
  `git init` repositories — no mocks. `conftest.py` provides `home` (isolated
  `HOME`/`USERPROFILE` so `~/.shed` and the config are per-test — use it in
  anything touching config or storage), `config_file`, and `make_repo`.
  CLI tests call `cli.main([...])` directly and assert on `capsys` output;
  interactive flows are driven by monkeypatching `builtins.input`
  (see `test_interactive.py`).
- Windows-only paths (junctions) are exercised via the `IS_WINDOWS` flag in
  `mount.py`; CI only runs Linux, so keep the platform split confined there.
