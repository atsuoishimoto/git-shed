# CLAUDE.md

Guidance for AI assistants working in this repository.

## What this project is

`git-shed` is a Python CLI tool — a repository-aware link manager for local
files kept outside Git. It resolves the canonical identity of a repository's
Git remotes (e.g. `github.com/acme/api`), matches them against shed
definitions in `~/.git-shed/config.toml`, creates storage directories
under `~/.git-shed/sheds/<name>` (the root is overridable via `GIT_SHED_ROOT`,
which moves the config file too), and links them into
the repository as `.shed/<name>` (symlinks on Linux/macOS, directory junctions
on Windows). Installed as `git-shed` on PATH so Git dispatches `git shed` to it.

The original design document (in Japanese) is `.plan/PLAN.md`; the README is
the authoritative user-facing description of current behavior.

## Layout

```
src/git_shed/        # the package (src layout, setuptools)
  cli.py             # argparse CLI: sync / add / link / unlink / remove /
                     #   status / list / path / open; entry point `main()`
  config.py          # config.toml load/edit via tomlkit; shed-name rules;
                     #   Shed dataclass; shed_path() and GIT_SHED_ROOT
  repository.py      # repo/remote discovery via `git`; Repository/Remote
                     #   dataclasses; MOUNTPOINT = ".shed"; shed.remote config
  identity.py        # remote URL -> canonical identity normalization
  matcher.py         # segment-wise pattern matching (`*`, `**`, case-insensitive)
  sync.py            # sync engine; SyncResult (added/removed/relinked/...)
  mount.py           # symlink / junction creation and removal (OS differences
                     #   are confined here)
  links.py           # .shed/.sheds list of explicitly linked sheds
  exclude.py         # keeps `/.shed/` in .git/info/exclude
  prompt.py          # interactive prompts
  errors.py          # GitShedError hierarchy (Usage/Config/Repository/
                     #   Remote/Mount); CLI maps them to stderr + non-zero exit
tests/               # pytest suite; conftest.py has `home` (isolated HOME),
                     #   `config_file`, `make_repo` fixtures
.plan/PLAN.md        # original design document (Japanese)
```

## Development commands

Requires Python 3.11+; the supported matrix is 3.11–3.14.

```bash
uvx uv-matrix run --max-jobs 4                    # tests on every interpreter
uvx uv-matrix run --filter python-version=3.13    # one interpreter
uv run --extra dev pytest                         # quick single-interpreter run
uv run --extra dev pytest tests/test_cli.py -k name   # one test

uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

CI (`.github/workflows/ci.yml`) runs exactly the matrix + both ruff commands
on Ubuntu. Tests shell out to real `git`, so a `user.name`/`user.email`/
`init.defaultBranch` git config must exist (CI sets one globally).

## Conventions

- Python 3.11+ typing; `from __future__ import annotations` in every module;
  frozen dataclasses for value types.
- Ruff is the only linter/formatter (rules `E,F,W,I,UP,B,SIM,RUF`,
  `target-version = py311`). Run both `ruff check` and `ruff format` before
  committing.
- Module docstrings explain each module's role and constraints — keep them
  accurate when changing behavior.
- User-facing errors derive from `GitShedError` and are raised, not printed;
  only the CLI layer talks to stdout/stderr. Warnings go to stderr prefixed
  `git shed: warning:`.
- Config file edits go through tomlkit so user comments/formatting survive.
- Tests never touch the real HOME: use the `home` fixture, `make_repo` for
  repositories, and `write_config` for config files.

## Safety invariants (do not break)

These are product guarantees, documented in README "Safety":

- Never delete shed data (`~/.git-shed/sheds/<name>`); only links/junctions in
  `repo/.shed/` may be removed.
- A real (non-link) file or directory inside `.shed/` is left untouched,
  with a warning.
- Only `.git/info/exclude` is modified — never `.gitignore`.
- A changed remote never moves or deletes anything.
- Exit code 0 when the command completed (no matching shed is not an error);
  non-zero for broken config, unresolvable repository/remote, missing input,
  or link-creation failure.

## Out of scope

Shed contents management (layout, backup, sync, encryption, secrets),
per-shed paths, orphan cleanup, GC, migration, shell completion. Not a
replacement for git-annex or Git LFS.
