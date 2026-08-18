"""Canonicalization of Git remote URLs into repository identities.

The identity is what shed patterns are matched against, so URLs that point at
the same repository must normalize to the same string::

    git@github.com:acme/foo.git
    https://github.com/acme/foo.git
    ssh://git@github.com/acme/foo
        -> github.com/acme/foo
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .errors import RemoteError

# scp-style SSH URL: [user@]host:path, where the part before ":" holds no "/".
_SCP_RE = re.compile(r"^(?:(?P<user>[^/@]+)@)?(?P<host>[^/:]+):(?P<path>.+)$")


def canonicalize(url: str) -> str:
    """Return the canonical repository identity for ``url``.

    The rules are: drop the protocol, drop the user name, lowercase the host,
    convert SCP-style SSH URLs to path form, then strip a leading "/", a
    trailing ".git" and a trailing "/".
    """
    raw = url.strip()
    if not raw:
        raise RemoteError("remote URL is empty")

    host, path = _split(raw)
    path = _clean_path(path)
    if not path:
        raise RemoteError(f"cannot interpret remote URL: {url}")

    return f"{host}/{path}" if host else path


def _split(url: str) -> tuple[str, str]:
    """Split ``url`` into a (lowercased host, path) pair."""
    if "://" in url:
        parts = urlsplit(url)
        if parts.scheme == "file":
            return "", parts.path
        if not parts.hostname:
            raise RemoteError(f"cannot interpret remote URL: {url}")
        return parts.hostname.lower(), parts.path

    if "::" in url:
        # Remote helper syntax, <transport>::<address>: no identity to derive.
        raise RemoteError(f"cannot interpret remote URL: {url}")

    scp = _SCP_RE.match(url)
    if scp:
        return scp.group("host").lower(), scp.group("path")

    if ":" in url or "@" in url:
        # Looks like a URL, but neither form parsed.
        raise RemoteError(f"cannot interpret remote URL: {url}")

    # Plain local path, e.g. /srv/git/foo.git or ../foo.
    return "", url


def _clean_path(path: str) -> str:
    path = path.replace("\\", "/")
    path = path.lstrip("/")
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return path.rstrip("/")
