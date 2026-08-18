"""The list of sheds linked explicitly, in ``.shed/.sheds``.

Sheds normally appear because the repository identity matches their patterns.
A shed listed in this file is linked as well, and ``sync`` leaves it alone --
it is there for the occasional reference that no match rule should describe.

The file holds one shed name per line; blank lines and ``#`` comments are
ignored.
"""

from __future__ import annotations

from pathlib import Path

from .errors import GitShedError

LINKS_FILE = ".sheds"


def path(mountpoint: Path) -> Path:
    return mountpoint / LINKS_FILE


def read(mountpoint: Path) -> tuple[str, ...]:
    """Return the shed names listed in ``.shed/.sheds``."""
    listing = path(mountpoint)
    if not listing.is_file():
        return ()
    try:
        text = listing.read_text(encoding="utf-8")
    except OSError as exc:
        raise GitShedError(f"cannot read {listing}: {exc}") from exc

    names: list[str] = []
    for line in text.splitlines():
        name = line.split("#", 1)[0].strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def add(mountpoint: Path, name: str) -> bool:
    """List ``name``; return False if it was listed already."""
    names = read(mountpoint)
    if name in names:
        return False
    _write(mountpoint, (*names, name))
    return True


def remove(mountpoint: Path, name: str) -> bool:
    """Drop ``name`` from the list; return False if it was not listed."""
    names = read(mountpoint)
    if name not in names:
        return False
    _write(mountpoint, tuple(other for other in names if other != name))
    return True


def _write(mountpoint: Path, names: tuple[str, ...]) -> None:
    listing = path(mountpoint)
    try:
        if not names:
            listing.unlink(missing_ok=True)
            return
        mountpoint.mkdir(parents=True, exist_ok=True)
        listing.write_text("".join(f"{name}\n" for name in names), encoding="utf-8")
    except OSError as exc:
        raise GitShedError(f"cannot write {listing}: {exc}") from exc
