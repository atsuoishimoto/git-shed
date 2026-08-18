# git-shed

[![CI](https://github.com/atsuoishimoto/git-shed/actions/workflows/ci.yml/badge.svg)](https://github.com/atsuoishimoto/git-shed/actions/workflows/ci.yml)

> A repository-aware link manager for local files kept outside Git.

`git-shed` prepares a storage directory ("shed") for each Git remote you work
with, and links it into the repository as `.shed/<name>`.

Notes, investigation SQL, debug scripts, local-only configuration, sample API
responses, scratch code, work notes for an AI, test data — things you want next
to a repository but not inside it.

```text
~/.shed/
├── company/
└── backend/

~/src/foo/
└── .shed/
    ├── company -> ~/.shed/company
    └── backend -> ~/.shed/backend
```

The real data lives outside the clone, so `rm -rf` on the clone keeps it, every
clone of the same remote sees the same shed, and several repositories can share
one shed. `git-shed` never looks inside a shed.

## Install

```bash
uv tool install git-shed
```

This puts `git-shed` on `PATH`, which is all Git needs to dispatch `git shed`.

## Tutorial

Clone a repository and ask for a shed. Nothing matches yet, so `sync` offers to
create one; the defaults come from the remote:

```text
$ git clone git@github.com:acme/api.git ~/src/api
$ cd ~/src/api
$ git shed sync

No shed matches:
  github.com/acme/api

Create a new shed? [Y/n] y

Shed name [api]:
Match pattern [github.com/acme/api]:

Create shed:
  name:  api
  match:
    - github.com/acme/api
  path:  /home/user/.shed/api

Create this shed? (y/n) y
Created shed:
  api

Linked:
  .shed/api -> /home/user/.shed/api
```

Write whatever you want under the link. It lives outside the clone, and Git
does not see it:

```bash
echo '# debugging notes' > .shed/api/notes.md
git status --short          # nothing, .shed/ is in .git/info/exclude
```

Check out a second working tree and run `sync` there too. It matches the same
remote, so it gets the same shed — the notes are already there:

```text
$ git worktree add ../api-hotfix hotfix
$ cd ../api-hotfix
$ git shed sync

Linked:
  .shed/api -> /home/user/.shed/api

$ cat .shed/api/notes.md
# debugging notes
```

Delete either working tree and `~/.shed/api` stays where it is.

## Configuration

`~/.config/git-shed/config.toml` (or `$XDG_CONFIG_HOME/git-shed/config.toml`):

```toml
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "backend"
match = [
  "github.com/acme/api",
  "github.com/acme/worker",
]

[[shed]]
name = "personal"
match = ["github.com/me/*"]
```

Sheds are not exclusive: `github.com/acme/api` matches both `company` and
`backend`, and gets both links.

A shed name starts with an ASCII letter or digit, continues with letters,
digits, `.`, `_` and `-`, and is at most 64 characters — the safe shape for a
directory name on every platform. Windows device names (`CON`, `NUL`, ...) and
a trailing `.` are rejected.

The data of a shed lives at `~/.shed/<name>`, by convention rather than by
configuration. `GIT_SHED_ROOT` moves that root elsewhere, for the whole tool:

```bash
export GIT_SHED_ROOT=/data/sheds        # -> /data/sheds/company
```

A leading `~` is expanded, since the variable is often set where a shell does
not expand it (`.env` files, systemd units, container environments). The value
has to denote an absolute path; a relative one is an error rather than
something resolved against the current directory.

## Usage

```bash
git shed sync              # create and drop links for the current repository
git shed sync --no-interactive
git shed add company 'github.com/acme/*' 'github.com/other/*'
git shed add company 'github.com/more/*'   # adds to the shed that exists
git shed add               # asks for whatever is missing
git shed link scratch      # link a shed here even though it does not match
git shed unlink scratch    # drop that link again
git shed remove company    # drops the definition, keeps the data
git shed remove company 'github.com/other/*'   # drops only these patterns
git shed status
git shed list              # matching sheds and their patterns
git shed list --all        # every defined shed and its patterns
git shed path company      # /home/user/.shed/company
git shed open company      # open it in the file manager
```

`git shed list` shows each shed with every pattern it is defined with, not only
the one that matched:

```text
$ git shed list
company
  github.com/acme/*
backend
  github.com/acme/api
  github.com/acme/worker
```

Shed names sit at the left margin and their patterns are indented, so
`git shed list | grep -v "^ "` still gives you plain names for a script.

`git shed add` takes a shed name followed by any number of patterns. Naming a
shed that already exists is not an error: its patterns are extended with the
ones you give, and a pattern it already has is reported instead of duplicated.
With no patterns on the command line it asks for one.

`git shed remove` with just a name drops the whole shed definition (never the
data). With patterns after the name it removes only those patterns and keeps
the shed; naming a pattern the shed does not have is an error.

`git shed sync` resolves the identities of the repository, creates
`~/.shed/<name>` and `repo/.shed/<name>` for every matching shed, drops the
links that no longer match, and adds `/.shed/` to `.git/info/exclude`.
`.gitignore` is never touched.

It reports what it did:

```text
Linked:
  .shed/company -> /home/user/.shed/company

Unlinked:
  .shed/old-shed
```

### One-off links

`git shed link <shed>` links a shed into the current repository even though no
match rule selects it — for the occasional reference that is not worth a
pattern. The name is recorded in `.shed/.sheds` (one per line, `#` comments
allowed), which is what keeps `sync` from dropping the link again:

```text
$ git shed link scratch

Linked:
  .shed/scratch -> /home/user/.shed/scratch
```

The shed does not have to be defined in the configuration: a name whose data
directory already exists under the storage root is enough, so a directory
created by hand can be linked without writing a match rule for it. A name with
neither a definition nor a directory is refused, which keeps a typo from
creating one.

`git shed unlink scratch` removes the entry and the link; the data stays. A
link that comes from the configuration is not `unlink`'s business — drop its
match rule instead.

When nothing matches the repository and the terminal is interactive, `sync`
offers to create a shed:

```text
$ git shed sync

No shed matches:
  github.com/acme/foo

Create a new shed? [Y/n] y

Shed name [foo]: company
Match pattern [github.com/acme/foo]: github.com/acme/*

Create shed:
  name:  company
  match:
    - github.com/acme/*
  path:  /home/user/.shed/company

Create this shed? (y/n) y
```

## Remote identity

Matching uses a canonical identity rather than the raw remote URL, so all of

```text
git@github.com:acme/foo.git
https://github.com/acme/foo.git
ssh://git@github.com/acme/foo
https://github.com/acme/foo
```

become

```text
github.com/acme/foo
```

Every remote contributes an identity, and the sheds matching any of them are
linked. In a fork checkout both the fork and the upstream repository are
matched without configuring anything:

```text
origin     git@github.com:me/foo.git       -> github.com/me/foo
upstream   git@github.com:acme/foo.git     -> github.com/acme/foo
```

To match on specific remotes only, name them — the setting is repeatable:

```bash
git config --local shed.remote upstream
git config --local --add shed.remote origin
```

A `shed.remote` naming a remote that does not exist is an error. A remote whose
URL cannot be interpreted is skipped with a warning, and the other remotes are
still used:

```text
git shed: warning: ignoring remote 'helper': cannot interpret remote URL: transport::address
```

A repository with no usable remote is identified by the name of its working
tree directory, so `~/src/notebook` gets the identity `notebook` and is matched
by a pattern of the same name:

```toml
[[shed]]
name = "notebook"
match = ["notebook"]
```

## Patterns

Identities are matched segment by segment:

```text
*    one segment
**   zero or more segments
```

```text
github.com/acme/foo
github.com/acme/*
gitlab.com/company/**
```

Matching is case-insensitive, and several sheds may match the same repository —
there is no priority or specificity rule to reason about.

## Safety

This tool holds data that is not in Git, so it stays away from anything
destructive.

- `sync` and `remove` only ever delete links / junctions, never shed data.
- A real file or directory inside `.shed/` is left alone, with a warning on
  stderr:

  ```text
  git shed: warning: .shed/notes is not a link, left untouched
  ```
- A changed remote does not move or delete anything; `status` shows the
  difference.
- Only `.git/info/exclude` is modified, never `.gitignore`.

## Platform support

Symbolic links on Linux and macOS, directory junctions on Windows. `.shed/`
itself is always a plain directory; only its entries are links.

Copying a project directory behaves differently on the two: `cp -r` keeps the
links, so the copy shares the same shed, while most Windows tools (Explorer,
`xcopy`, `robocopy`, `Copy-Item`) follow a junction and duplicate what is
behind it — use `robocopy /XJ` to leave junctions out. Running `git shed sync`
in the copy restores the links either way.

## Exit codes

`0` when the command completed — a repository matching no shed is not an error.
Non-zero for a broken configuration file, a repository or remote that cannot be
resolved, missing input for `add`, or a link that cannot be created.

## Not in scope

The contents of a shed (layout, name collisions, backup, sync, encryption,
secrets), per-shed paths, orphan cleanup, GC, migration and shell completion. It is not a replacement for git-annex or Git
LFS.

## Development

The test suite runs on Python 3.11 through 3.14. That matrix lives under
`[tool.uv-matrix]` in `pyproject.toml` and is driven by
[uv-matrix](https://uv-matrix.readthedocs.io/); ruff needs no matrix:

```bash
uvx uv-matrix run --max-jobs 4       # the suite on every interpreter
uvx uv-matrix list                   # what the matrix expands to
uvx uv-matrix run --filter python-version=3.13

uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

CI runs exactly these commands on Ubuntu. A single interpreter without uv works
too:

```bash
pip install -e ".[dev]"
python -m pytest
```
