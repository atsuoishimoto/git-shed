"""Synchronizing ``repo/.shed/`` with the sheds matching the repository."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import links as linkslib
from . import mount as mountlib
from .config import Shed, shed_path
from .errors import MountError
from .exclude import ensure_excluded
from .repository import MOUNTPOINT, Repository


@dataclass
class SyncResult:
    """What ``sync`` changed in ``repo/.shed/``."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    relinked: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    excluded: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.relinked)

    @property
    def warnings(self) -> list[str]:
        """Messages for the entries in ``.shed/`` that were left alone."""
        return [
            f"{MOUNTPOINT}/{name} is not a link, shed not linked"
            for name in self.blocked
        ] + [
            f"{MOUNTPOINT}/{name} is not a link, left untouched"
            for name in self.skipped
        ]


def sync(
    repo: Repository,
    sheds: tuple[Shed, ...],
    keep: frozenset[str] = frozenset(),
) -> SyncResult:
    """Create the links for ``sheds`` and drop the links that no longer match.

    Names in ``keep`` are never dropped, even when nothing matches them.
    """
    result = SyncResult()
    mountpoint = repo.mountpoint
    wanted = {shed.name: shed_path(shed.name) for shed in sheds}

    for name, target in wanted.items():
        target.mkdir(parents=True, exist_ok=True)
        link = mountpoint / name
        current = _current_target(link)
        if current is None and (link.exists() or link.is_symlink()):
            # A real file or directory sits where the link should be.
            result.blocked.append(name)
            continue
        if current is None:
            mountlib.mount(link, target)
            result.added.append(name)
        elif _same_path(current, target):
            result.unchanged.append(name)
        else:
            mountlib.unmount(link)
            mountlib.mount(link, target)
            result.relinked.append(name)

    for link in _entries(mountpoint):
        if link.name in wanted or link.name in keep:
            continue
        if link.name == linkslib.LINKS_FILE:
            continue
        if not mountlib.is_mount(link):
            result.skipped.append(link.name)
            continue
        mountlib.unmount(link)
        result.removed.append(link.name)

    result.added.sort()
    result.removed.sort()
    result.relinked.sort()
    result.unchanged.sort()
    result.blocked.sort()
    result.skipped.sort()

    if wanted or mountpoint.exists():
        result.excluded = ensure_excluded(repo.git_common_dir)
    return result


def _entries(mountpoint: Path) -> list[Path]:
    if not mountpoint.is_dir():
        return []
    return sorted(mountpoint.iterdir())


def _current_target(link: Path) -> Path | None:
    try:
        return mountlib.mount_target(link)
    except MountError:
        return None


def _same_path(left: Path, right: Path) -> bool:
    return str(left).rstrip("/\\") == str(right).rstrip("/\\")
