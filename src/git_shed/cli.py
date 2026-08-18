"""Command line interface for git-shed.

Installed as ``git-shed`` on PATH, which makes Git dispatch ``git shed`` to it.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from pathlib import Path

from . import config as configlib
from . import links as linkslib
from . import mount as mountlib
from . import prompt as promptlib
from .config import Config, Shed, shed_path
from .errors import GitShedError, UsageError
from .repository import MOUNTPOINT, Repository, discover
from .sync import sync as sync_mounts

PROG = "git shed"


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose help option is just "-h"."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self.add_argument("-h", action="help", help="show this help message and exit")
        # Still honored when the program is run directly as git-shed --help;
        # just not advertised, since "git shed --help" never gets this far.
        self.add_argument("--help", action="help", help=argparse.SUPPRESS)


def _parser(**kwargs) -> argparse.ArgumentParser:
    return _Parser(**kwargs)


def build_parser() -> argparse.ArgumentParser:
    # add_help is off and only "-h" is registered: "git shed --help" never
    # reaches this program (git turns it into a man-page lookup), so
    # advertising "--help" would point at the option that does not work.
    parser = _parser(
        prog=PROG,
        description="Link sheds -- directories kept outside Git -- into a repository.",
    )
    subparsers = parser.add_subparsers(dest="command", parser_class=type(parser))

    sync_parser = subparsers.add_parser(
        "sync", help="create and drop the links in .shed/ for the current repository"
    )
    sync_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="never prompt; do not offer to create a shed when nothing matches",
    )
    sync_parser.set_defaults(func=cmd_sync)

    add_parser = subparsers.add_parser(
        "add", help="define a shed, or add match patterns to one that exists"
    )
    add_parser.add_argument("name", nargs="?", help="shed name")
    add_parser.add_argument(
        "patterns",
        nargs="*",
        metavar="PATTERN",
        help="identity patterns to match; asked for when none are given",
    )
    add_parser.set_defaults(func=cmd_add)

    link_parser = subparsers.add_parser(
        "link", help="link a shed into this repository regardless of the match rules"
    )
    link_parser.add_argument("name", help="shed name")
    link_parser.set_defaults(func=cmd_link)

    unlink_parser = subparsers.add_parser("unlink", help="drop a link made with 'link'")
    unlink_parser.add_argument("name", help="shed name")
    unlink_parser.set_defaults(func=cmd_unlink)

    remove_parser = subparsers.add_parser(
        "remove", help="remove a shed definition, or just some of its match patterns"
    )
    remove_parser.add_argument("name", help="shed name")
    remove_parser.add_argument(
        "patterns",
        nargs="*",
        metavar="PATTERN",
        help="remove only these patterns instead of the whole shed",
    )
    remove_parser.set_defaults(func=cmd_remove)

    status_parser = subparsers.add_parser(
        "status", help="show the repository identity, its sheds and its mounts"
    )
    status_parser.set_defaults(func=cmd_status)

    list_parser = subparsers.add_parser("list", help="list the matching sheds")
    list_parser.add_argument(
        "--all", action="store_true", help="list every defined shed instead"
    )
    list_parser.set_defaults(func=cmd_list)

    path_parser = subparsers.add_parser("path", help="print the data path of a shed")
    path_parser.add_argument("name", help="shed name")
    path_parser.set_defaults(func=cmd_path)

    open_parser = subparsers.add_parser(
        "open", help="open the data directory of a shed in the file manager"
    )
    open_parser.add_argument("name", help="shed name")
    open_parser.set_defaults(func=cmd_open)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except GitShedError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # Downstream of a pipe went away, as in "git shed status | head".
        _discard_stdout()
        return 128 + 13


# --- commands ---------------------------------------------------------------


def cmd_sync(args: argparse.Namespace) -> int:
    repo = _discover()
    config = configlib.load()
    sheds = _wanted(repo, config)

    if not sheds:
        _report(("No shed matches:", list(repo.identities)))
        if args.no_interactive or not promptlib.interactive():
            return 0
        print()
        if not promptlib.confirm("Create a new shed?"):
            return 0
        shed = _define_shed(config, repo)
        if shed is None:
            return 0
        print()
        config = configlib.load()
        sheds = _wanted(repo, config)
        if not sheds:
            _report(("No shed matches:", list(repo.identities)))
            return 0

    return _sync(repo, sheds)


def cmd_link(args: argparse.Namespace) -> int:
    repo = _discover()
    config = configlib.load()
    if _resolve(config, args.name) is None:
        raise UsageError(
            f"no shed named {args.name}: it is not in {config.path} "
            f"and {shed_path(args.name)} does not exist"
        )

    if not linkslib.add(repo.mountpoint, args.name):
        print(f"{MOUNTPOINT}/{args.name} is already linked")
    return _sync(repo, _wanted(repo, config))


def cmd_unlink(args: argparse.Namespace) -> int:
    repo = _discover()
    config = configlib.load()
    link = repo.mountpoint / args.name

    if args.name not in linkslib.read(repo.mountpoint):
        if mountlib.is_mount(link):
            raise UsageError(
                f"{MOUNTPOINT}/{args.name} was not linked with 'link'; "
                "it comes from the configuration"
            )
        raise UsageError(f"{MOUNTPOINT}/{args.name} is not linked")

    linkslib.remove(repo.mountpoint, args.name)
    if mountlib.is_mount(link):
        mountlib.unmount(link)
    _report(("Unlinked:", [f"{MOUNTPOINT}/{args.name}"]))

    shed = config.get(args.name)
    if shed is not None and shed.matches(repo.identities):
        _warn(f"{args.name} matches this repository; the next sync links it again")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    config = configlib.load()
    repo = _try_discover()
    shed = _define_shed(config, repo, name=args.name, patterns=list(args.patterns))
    return 0 if shed is not None else 1


def cmd_remove(args: argparse.Namespace) -> int:
    config = configlib.load()
    shed = config.get(args.name)
    if shed is None:
        raise UsageError(f"no shed named {args.name}")

    if args.patterns:
        return _remove_patterns(config, shed, args.patterns)

    configlib.remove_shed(config.path, args.name)
    print(f"Removed shed:\n  {args.name}")

    repo = _try_discover()
    if repo is not None:
        linkslib.remove(repo.mountpoint, args.name)
        link = repo.mountpoint / args.name
        if mountlib.is_mount(link):
            mountlib.unmount(link)
            print(f"Unlinked:\n  {MOUNTPOINT}/{args.name}")

    print(f"Data kept at:\n  {shed_path(args.name)}")
    return 0


def _remove_patterns(config: Config, shed: Shed, patterns: list[str]) -> int:
    """Drop the given patterns from ``shed``, keeping the shed itself."""
    unknown = [pattern for pattern in patterns if pattern not in shed.match]
    if unknown:
        raise UsageError(f"shed {shed.name} has no pattern {unknown[0]}")

    configlib.remove_patterns(config.path, shed.name, patterns)
    print(f"Updated shed:\n  {shed.name}")
    remaining = [pattern for pattern in shed.match if pattern not in patterns]
    if not remaining:
        print(f"No patterns left; 'remove {shed.name}' drops the shed itself.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo = _discover()
    config = configlib.load()
    sheds = _wanted(repo, config)
    listed = linkslib.read(repo.mountpoint)

    print("repository:")
    if repo.has_remote:
        width = max(len(remote.identity) for remote in repo.remotes)
        for remote in repo.remotes:
            print(f"  {remote.identity.ljust(width)}  ({remote.name})")
    else:
        print(f"  {repo.identity}  (no remote, using the directory name)")

    print("\nsheds:")
    if not sheds:
        print("  (none)")
    else:
        width = max(len(shed.name) for shed in sheds)
        for shed in sheds:
            reasons = list(shed.matched_patterns(repo.identities))
            if shed.name in listed:
                reasons.append("(linked)")
            print(f"  {shed.name.ljust(width)}  {', '.join(reasons)}")

    print("\nmounts:")
    wanted = {shed.name for shed in sheds} | set(listed)
    lines: list[str] = []
    for name in sorted(wanted):
        link = repo.mountpoint / name
        if not mountlib.is_mount(link):
            lines.append(f"  {MOUNTPOINT}/{name} (missing)")
        elif str(mountlib.mount_target(link)) != str(shed_path(name)):
            target = mountlib.mount_target(link)
            lines.append(f"  {MOUNTPOINT}/{name} -> {target} (unexpected target)")
        else:
            lines.append(f"  {MOUNTPOINT}/{name}")
    if repo.mountpoint.is_dir():
        for entry in sorted(repo.mountpoint.iterdir()):
            if entry.name in wanted or entry.name == linkslib.LINKS_FILE:
                continue
            state = "stale" if mountlib.is_mount(entry) else "not a link"
            lines.append(f"  {MOUNTPOINT}/{entry.name} ({state})")
    print("\n".join(lines) if lines else "  (none)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = configlib.load()
    if args.all:
        sheds = config.sheds
    else:
        repo = _discover()
        sheds = config.matching(repo.identities)
    # The name on its own line, its patterns indented under it: readable with
    # several patterns, and "grep -v '^ '" still yields plain shed names.
    for shed in sheds:
        print(shed.name)
        for pattern in shed.match:
            print(f"  {pattern}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    config = configlib.load()
    if _resolve(config, args.name) is None:
        raise UsageError(f"no shed named {args.name}")
    print(shed_path(args.name))
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    config = configlib.load()
    if _resolve(config, args.name) is None:
        raise UsageError(f"no shed named {args.name}")
    target = shed_path(args.name)
    target.mkdir(parents=True, exist_ok=True)
    _open_in_file_manager(target)
    return 0


# --- helpers ----------------------------------------------------------------


def _wanted(repo: Repository, config: Config) -> tuple[Shed, ...]:
    """The sheds matching the repository, plus the explicitly linked ones."""
    sheds = list(config.matching(repo.identities))
    known = {shed.name for shed in sheds}
    for name in linkslib.read(repo.mountpoint):
        if name in known:
            continue
        shed = _resolve(config, name)
        if shed is None:
            _warn(
                f"unknown shed '{name}' in {MOUNTPOINT}/{linkslib.LINKS_FILE}: "
                f"no definition and no directory at {shed_path(name)}"
            )
            continue
        sheds.append(shed)
        known.add(name)
    return tuple(sheds)


def _resolve(config: Config, name: str) -> Shed | None:
    """The shed called ``name``, defined in the configuration or existing on disk."""
    shed = config.get(name)
    if shed is not None:
        return shed
    if shed_path(name).is_dir():
        # No definition, but the data is there: usable as a one-off link.
        return Shed(name=name, match=())
    return None


def _sync(repo: Repository, sheds: tuple[Shed, ...]) -> int:
    """Bring ``.shed/`` in line with ``sheds`` and report what changed."""
    result = sync_mounts(repo, sheds, keep=frozenset(linkslib.read(repo.mountpoint)))
    _report(
        ("Linked:", [_link_line(name) for name in result.added]),
        ("Relinked:", [_link_line(name) for name in result.relinked]),
        ("Unlinked:", [f"{MOUNTPOINT}/{name}" for name in result.removed]),
    )
    for message in result.warnings:
        _warn(message)
    if not result.changed and not result.warnings:
        print("Already in sync.")
    return 0


def _discard_stdout() -> None:
    """Keep the interpreter from reporting the broken pipe again on exit."""
    with contextlib.suppress(AttributeError, OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _report(*sections: tuple[str, list[str]]) -> None:
    """Print the non-empty ``(title, lines)`` sections, one blank line apart."""
    printed = False
    for title, lines in sections:
        if not lines:
            continue
        if printed:
            print()
        print(title)
        for line in lines:
            print(f"  {line}")
        printed = True


def _link_line(name: str) -> str:
    return f"{MOUNTPOINT}/{name} -> {shed_path(name)}"


def _warn(message: str) -> None:
    print(f"{PROG}: warning: {message}", file=sys.stderr)


def _discover() -> Repository:
    """Discover the repository, reporting the remotes that were ignored."""
    repo = discover()
    for message in repo.warnings:
        _warn(message)
    return repo


def _try_discover() -> Repository | None:
    try:
        return _discover()
    except GitShedError:
        return None


def _define_shed(
    config: Config,
    repo: Repository | None,
    name: str | None = None,
    patterns: list[str] | None = None,
) -> Shed | None:
    """Define a shed, or add patterns to one that exists, asking for what is missing."""
    patterns = list(patterns or [])
    asked = False

    if name is None:
        if not promptlib.interactive():
            raise UsageError("shed name is required")
        asked = True
        name = promptlib.ask("Shed name", _default_name(repo))
    name = configlib.validate_name(name)
    existing = config.get(name)

    if not patterns:
        if not promptlib.interactive():
            raise UsageError("at least one match pattern is required")
        asked = True
        # One pattern is enough to get going; more are added by running add again.
        patterns.append(promptlib.ask("Match pattern", _default_pattern(repo)))

    known = existing.match if existing else ()
    added: list[str] = []
    for pattern in patterns:
        if pattern not in known and pattern not in added:
            added.append(pattern)

    if existing is not None and not added:
        print(f"Already matched by shed:\n  {name}")
        return existing

    if asked and not _confirm_shed(name, added, update=existing is not None):
        return None

    if existing is None:
        shed = Shed(name=name, match=tuple(added))
        configlib.append_shed(config.path, shed)
        print(f"Created shed:\n  {name}")
        return shed

    configlib.add_patterns(config.path, name, added)
    print(f"Updated shed:\n  {name}")
    return Shed(name=name, match=(*existing.match, *added))


def _confirm_shed(name: str, patterns: list[str], *, update: bool) -> bool:
    """Show what is about to be written and ask for an explicit yes or no."""
    print(f"\n{'Add to shed' if update else 'Create shed'}:")
    print(f"  name:  {name}")
    print("  match:")
    for pattern in patterns:
        print(f"    - {pattern}")
    print(f"  path:  {shed_path(name)}{_path_note(name)}\n")
    question = "Add these patterns?" if update else "Create this shed?"
    return promptlib.confirm(question, default=None)


def _path_note(name: str) -> str:
    """Say whether the data directory of ``name`` is already there."""
    target = shed_path(name)
    if target.is_dir():
        return "  (exists; its contents are kept)"
    if target.exists():
        return "  (exists but is not a directory)"
    return ""


def _default_name(repo: Repository | None) -> str | None:
    if repo is None:
        return None
    return repo.identity.rsplit("/", 1)[-1] or None


def _default_pattern(repo: Repository | None) -> str | None:
    return repo.identity if repo is not None else None


def _open_in_file_manager(target: Path) -> None:
    if sys.platform == "darwin":
        command = ["open", str(target)]
    elif sys.platform == "win32":
        command = ["explorer", str(target)]
    else:
        command = ["xdg-open", str(target)]
    try:
        subprocess.run(command, check=False)
    except OSError as exc:
        raise GitShedError(f"cannot open {target}: {exc}") from exc
