"""Creating and removing the links inside ``.shed/``.

Unix uses symbolic links, Windows uses directory junctions.  Only links are
ever removed here -- the shed data itself is never touched.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .errors import MountError

IS_WINDOWS = sys.platform == "win32"


def is_mount(path: Path) -> bool:
    """Return True if ``path`` is a symlink or a directory junction."""
    if path.is_symlink():
        return True
    if IS_WINDOWS and path.exists():
        try:
            os.readlink(path)
        except OSError:
            return False
        return True
    return False


def mount_target(path: Path) -> Path | None:
    """Return the target of the link at ``path``, or None if it is not a link."""
    if not is_mount(path):
        return None
    try:
        return Path(os.readlink(path))
    except OSError as exc:
        raise MountError(f"cannot read link {path}: {exc}") from exc


def mount(path: Path, target: Path) -> None:
    """Link ``path`` to the directory ``target``."""
    if path.exists() or path.is_symlink():
        raise MountError(f"{path} already exists")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MountError(f"cannot create {path.parent}: {exc}") from exc

    if IS_WINDOWS:
        _mount_junction(path, target)
        return
    try:
        path.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        raise MountError(f"cannot link {path} -> {target}: {exc}") from exc


def unmount(path: Path) -> None:
    """Remove the link at ``path``; refuse to touch anything else."""
    if not is_mount(path):
        raise MountError(f"{path} is not a link, refusing to remove it")
    try:
        if IS_WINDOWS and path.is_dir():
            os.rmdir(path)
        else:
            path.unlink()
    except OSError as exc:
        raise MountError(f"cannot remove link {path}: {exc}") from exc


def _mount_junction(path: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(path), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise MountError(f"cannot create junction {path} -> {target}: {message}")
