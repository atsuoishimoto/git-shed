"""Keeping ``/.shed/`` in ``.git/info/exclude``.

``.gitignore`` is never modified: the mountpoint is a local concern and must
not leak into what the team shares.
"""

from __future__ import annotations

from pathlib import Path

from .errors import GitShedError

EXCLUDE_LINE = "/.shed/"


def ensure_excluded(git_common_dir: Path) -> bool:
    """Add ``/.shed/`` to info/exclude if missing; return True if it was added."""
    path = git_common_dir / "info" / "exclude"
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise GitShedError(f"cannot read {path}: {exc}") from exc

    if any(line.strip() == EXCLUDE_LINE for line in text.splitlines()):
        return False

    prefix = "" if not text or text.endswith("\n") else "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{prefix}{EXCLUDE_LINE}\n")
    except OSError as exc:
        raise GitShedError(f"cannot write {path}: {exc}") from exc
    return True
