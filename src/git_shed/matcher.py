"""Pattern matching between shed match rules and repository identities.

Identities are treated as "/" separated segments::

    *   matches exactly one segment
    **  matches zero or more segments

A "*" may also cover part of a segment ("acme-*", "repo_*"); each segment is
matched with :func:`fnmatch.fnmatchcase`.
"""

from __future__ import annotations

from fnmatch import fnmatchcase


def matches(pattern: str, identity: str) -> bool:
    """Return True if ``identity`` matches ``pattern``."""
    pattern = pattern.strip().strip("/")
    if not pattern:
        return False
    return _match(pattern.lower().split("/"), identity.lower().split("/"))


def _match(patterns: list[str], segments: list[str]) -> bool:
    if not patterns:
        return not segments
    head, rest = patterns[0], patterns[1:]
    if head == "**":
        # "**" consumes zero or more segments.
        return any(_match(rest, segments[i:]) for i in range(len(segments) + 1))
    if not segments:
        return False
    return fnmatchcase(segments[0], head) and _match(rest, segments[1:])
