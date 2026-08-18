"""Exceptions used across git-shed.

All errors that are expected to be reported to the user derive from
:class:`GitShedError`; the CLI turns them into a message on stderr and a
non-zero exit code.
"""

from __future__ import annotations


class GitShedError(Exception):
    """Base class for errors reported to the user."""


class UsageError(GitShedError):
    """The command line arguments or the interactive input were not usable."""


class ConfigError(GitShedError):
    """The configuration file could not be parsed or is invalid."""


class RepositoryError(GitShedError):
    """The Git repository could not be discovered or queried."""


class RemoteError(GitShedError):
    """The remote could not be resolved or its URL could not be interpreted."""


class MountError(GitShedError):
    """A link / junction could not be created or removed."""
