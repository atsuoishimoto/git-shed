"""Discovery of the current Git repository and its identities.

Every remote of the repository contributes an identity, so a fork checkout
matches the sheds of both its own remote and the upstream one.  ``shed.remote``
narrows that down to the named remotes.  A remote whose URL cannot be
interpreted is reported as a warning and skipped; a repository with no usable
remote at all falls back to the name of its working tree directory.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import RemoteError, RepositoryError
from .identity import canonicalize

DEFAULT_REMOTE = "origin"
MOUNTPOINT = ".shed"


@dataclass(frozen=True)
class Remote:
    """A remote of the repository and the identity it resolves to."""

    name: str
    url: str
    identity: str


@dataclass(frozen=True)
class Repository:
    """The repository git-shed is operating on."""

    root: Path
    git_common_dir: Path
    remotes: tuple[Remote, ...]
    identities: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def identity(self) -> str:
        """The identity used for defaults and messages (the first one)."""
        return self.identities[0]

    @property
    def has_remote(self) -> bool:
        return bool(self.remotes)

    @property
    def mountpoint(self) -> Path:
        return self.root / MOUNTPOINT


def run_git(args: list[str], cwd: Path) -> str:
    """Run ``git`` and return its stdout, or raise on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RepositoryError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RepositoryError(f"git {' '.join(args)} failed: {message}")
    return result.stdout.strip()


def _git_config_all(name: str, cwd: Path) -> list[str]:
    """Return every value configured for ``name`` (an empty list if unset)."""
    result = subprocess.run(
        ["git", "config", "--get-all", name],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def discover(cwd: Path | None = None) -> Repository:
    """Return the repository containing ``cwd`` and the identities it matches."""
    cwd = Path(cwd) if cwd else Path.cwd()

    try:
        root = Path(run_git(["rev-parse", "--show-toplevel"], cwd))
    except RepositoryError as exc:
        raise RepositoryError(f"not inside a Git repository: {cwd}") from exc

    common_dir = Path(run_git(["rev-parse", "--git-common-dir"], cwd))
    if not common_dir.is_absolute():
        common_dir = (cwd / common_dir).resolve()

    remotes, warnings = _resolve_remotes(cwd)
    identities = _unique(remote.identity for remote in remotes)
    if not identities:
        # No usable remote: fall back to the name of the working tree.
        identities = (_directory_identity(root),)

    return Repository(
        root=root,
        git_common_dir=common_dir,
        remotes=remotes,
        identities=identities,
        warnings=tuple(warnings),
    )


def _resolve_remotes(cwd: Path) -> tuple[tuple[Remote, ...], list[str]]:
    """Resolve the remotes to match on, skipping the ones that make no sense."""
    available = run_git(["remote"], cwd).split()
    configured = _git_config_all("shed.remote", cwd)
    if configured:
        missing = [name for name in configured if name not in available]
        if missing:
            raise RemoteError(f"remote '{missing[0]}' does not exist")
        names = configured
    else:
        # origin first, so that it provides the defaults of the interactive setup.
        names = sorted(available, key=lambda name: (name != DEFAULT_REMOTE, name))

    remotes: list[Remote] = []
    warnings: list[str] = []
    for name in names:
        try:
            url = run_git(["remote", "get-url", name], cwd)
        except RepositoryError as exc:
            warnings.append(f"ignoring remote '{name}': {exc}")
            continue
        try:
            identity = canonicalize(url)
        except RemoteError as exc:
            warnings.append(f"ignoring remote '{name}': {exc}")
            continue
        remotes.append(Remote(name=name, url=url, identity=identity))

    return tuple(remotes), warnings


def _unique(values) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)


def _directory_identity(root: Path) -> str:
    name = root.resolve().name
    if not name:
        raise RemoteError(f"cannot derive a repository name from {root}")
    return name
