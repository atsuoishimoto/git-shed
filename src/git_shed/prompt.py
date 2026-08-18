"""Small helpers for the interactive mode."""

from __future__ import annotations

import sys

from .errors import UsageError


def interactive() -> bool:
    """Return True if we may prompt the user."""
    return sys.stdin is not None and sys.stdin.isatty()


def ask(question: str, default: str | None = None, *, required: bool = True) -> str:
    """Ask for a string, offering ``default`` when there is one."""
    label = f"{question} [{default}]: " if default else f"{question}: "
    while True:
        answer = _readline(label).strip()
        if answer:
            return answer
        if default:
            return default
        if not required:
            return ""
        print("A value is required.")


def confirm(question: str, default: bool | None = True) -> bool:
    """Ask a yes/no question; ``default`` of None demands an explicit answer."""
    if default is None:
        label = f"{question} (y/n) "
    else:
        label = f"{question} [{'Y/n' if default else 'y/N'}] "
    while True:
        answer = _readline(label).strip().lower()
        if not answer and default is not None:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _readline(label: str) -> str:
    try:
        return input(label)
    except EOFError as exc:
        raise UsageError("no input available") from exc
    except KeyboardInterrupt:
        print()
        raise UsageError("aborted") from None
