"""Loading and editing the shed configuration file.

The configuration lives in ``~/.config/git-shed/config.toml`` (or under
``$XDG_CONFIG_HOME``) and looks like::

    [[shed]]
    name = "company"
    match = ["github.com/acme/*"]

Reading and writing both go through :mod:`tomlkit`, so comments and the
formatting the user added survive an edit.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import tomlkit
import tomlkit.exceptions

from .errors import ConfigError

STORAGE_ROOT_ENV = "GIT_SHED_ROOT"

# A shed name doubles as a directory name on every platform and as a line in
# .shed/.sheds, so it is restricted to a safe shape: an ASCII letter or digit
# first, then letters, digits, ".", "_" and "-". Windows device names are
# unusable as directories there and rejected outright.
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NAME_MAX = 64
_WINDOWS_RESERVED = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{digit}" for digit in "123456789"]
    + [f"lpt{digit}" for digit in "123456789"]
)


@dataclass(frozen=True)
class Shed:
    """A shed definition: a name and the identity patterns it matches."""

    name: str
    match: tuple[str, ...]

    def matched_patterns(self, identities: Iterable[str]) -> tuple[str, ...]:
        """Return the patterns of this shed that match any of ``identities``."""
        from .matcher import matches

        identities = _as_tuple(identities)
        return tuple(
            pattern
            for pattern in self.match
            if any(matches(pattern, identity) for identity in identities)
        )

    def matches(self, identities: Iterable[str]) -> bool:
        return bool(self.matched_patterns(identities))


@dataclass(frozen=True)
class Config:
    """The parsed configuration file."""

    path: Path
    sheds: tuple[Shed, ...]

    def get(self, name: str) -> Shed | None:
        for shed in self.sheds:
            if shed.name == name:
                return shed
        return None

    def matching(self, identities: Iterable[str]) -> tuple[Shed, ...]:
        """Return the sheds matching any of ``identities``."""
        identities = _as_tuple(identities)
        return tuple(shed for shed in self.sheds if shed.matches(identities))


def _as_tuple(identities: Iterable[str]) -> tuple[str, ...]:
    """Accept a single identity as well as a collection of them."""
    if isinstance(identities, str):
        return (identities,)
    return tuple(identities)


def config_path() -> Path:
    """Return the path of the configuration file."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "git-shed" / "config.toml"


def storage_root() -> Path:
    """Return the directory holding the shed data.

    ``~/.shed`` by convention; ``GIT_SHED_ROOT`` overrides it. A leading ``~``
    is expanded, since the variable is often set where a shell does not expand
    it, but the value has to denote an absolute path.
    """
    override = os.environ.get(STORAGE_ROOT_ENV, "").strip()
    if not override:
        return Path.home() / ".shed"

    root = Path(os.path.expanduser(override))
    if not root.is_absolute():
        raise ConfigError(f"{STORAGE_ROOT_ENV} must be an absolute path: {override}")
    return root


def shed_path(name: str) -> Path:
    """Return the data directory of the shed called ``name``."""
    return storage_root() / name


def validate_name(name: str) -> str:
    """Return ``name`` if it is usable as a shed name, else raise."""
    name = name.strip()
    if not name:
        raise ConfigError("shed name must not be empty")
    if len(name) > _NAME_MAX:
        raise ConfigError(f"shed name is longer than {_NAME_MAX} characters: {name}")
    if not _NAME_RE.fullmatch(name):
        raise ConfigError(
            f"invalid shed name: {name} "
            "(use letters, digits, '.', '_' and '-', starting with a letter or digit)"
        )
    if name.endswith("."):
        raise ConfigError(f"invalid shed name: {name} (must not end with '.')")
    if name.split(".", 1)[0].lower() in _WINDOWS_RESERVED:
        raise ConfigError(f"invalid shed name: {name} (reserved name on Windows)")
    return name


def load(path: Path | None = None) -> Config:
    """Load the configuration file; a missing file yields an empty config."""
    path = path or config_path()
    if not path.exists():
        return Config(path=path, sheds=())

    return Config(path=path, sheds=_parse_sheds(_read(path).unwrap(), path))


def _parse_sheds(data: dict, path: Path) -> tuple[Shed, ...]:
    entries = data.get("shed", [])
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'shed' must be an array of tables")

    sheds: list[Shed] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: 'shed' must be an array of tables")

        name = entry.get("name")
        if not isinstance(name, str):
            raise ConfigError(f"{path}: every shed needs a string 'name'")
        name = validate_name(name)
        if name in seen:
            raise ConfigError(f"{path}: duplicate shed name: {name}")
        seen.add(name)

        patterns = entry.get("match", [])
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list) or not all(
            isinstance(pattern, str) for pattern in patterns
        ):
            raise ConfigError(
                f"{path}: shed '{name}': 'match' must be a list of strings"
            )

        sheds.append(Shed(name=name, match=tuple(patterns)))

    return tuple(sheds)


def append_shed(path: Path, shed: Shed) -> None:
    """Append a shed definition to the configuration file."""
    document = _read(path) if path.exists() else tomlkit.document()

    sheds = document.get("shed")
    if sheds is None:
        sheds = tomlkit.aot()
        document["shed"] = sheds

    table = tomlkit.table()
    if len(document.body) > 1 or len(sheds) > 0:
        # Keep a blank line between this table and whatever precedes it.
        table.trivia.indent = "\n"
    table["name"] = shed.name
    patterns = tomlkit.array()
    patterns.extend(shed.match)
    if len(shed.match) > 1:
        patterns.multiline(True)
    table["match"] = patterns
    sheds.append(table)

    _write(path, document)


def add_patterns(path: Path, name: str, patterns: Iterable[str]) -> None:
    """Append match patterns to the shed called ``name``."""
    document = _read(path)

    for entry in document.get("shed") or []:
        if entry.get("name") != name:
            continue
        match = entry.get("match")
        if not isinstance(match, list):
            replacement = tomlkit.array()
            if isinstance(match, str):
                replacement.append(match)
            entry["match"] = replacement
            match = entry["match"]
        for pattern in patterns:
            match.append(pattern)
        _write(path, document)
        return

    raise ConfigError(f"{path}: no shed named {name}")


def remove_patterns(path: Path, name: str, patterns: Iterable[str]) -> None:
    """Remove match patterns from the shed called ``name``."""
    document = _read(path)

    for entry in document.get("shed") or []:
        if entry.get("name") != name:
            continue
        match = entry.get("match")
        current = list(match) if isinstance(match, list) else []
        for pattern in patterns:
            current.remove(pattern)
        replacement = tomlkit.array()
        if len(current) > 1:
            replacement.multiline(True)
        replacement.extend(current)
        entry["match"] = replacement
        _write(path, document)
        return

    raise ConfigError(f"{path}: no shed named {name}")


def remove_shed(path: Path, name: str) -> None:
    """Remove the ``[[shed]]`` table called ``name`` from the file."""
    document = _read(path)
    sheds = document.get("shed") or []

    for index, entry in enumerate(sheds):
        if entry.get("name") == name:
            sheds.pop(index)
            break
    else:
        raise ConfigError(f"{path}: no shed named {name}")

    if not len(sheds):
        del document["shed"]
    _write(path, document)


def _read(path: Path) -> tomlkit.TOMLDocument:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        return tomlkit.parse(text)
    except tomlkit.exceptions.ParseError as exc:
        raise ConfigError(f"cannot parse {path}: {exc}") from exc


def _write(path: Path, document: tomlkit.TOMLDocument) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(document), encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot write {path}: {exc}") from exc
