from __future__ import annotations

import pytest

from git_shed.errors import RemoteError
from git_shed.identity import canonicalize


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:acme/foo.git",
        "https://github.com/acme/foo.git",
        "ssh://git@github.com/acme/foo.git",
        "https://github.com/acme/foo",
        "https://GitHub.com/acme/foo/",
        "https://user:token@github.com/acme/foo.git",
        "ssh://git@github.com:22/acme/foo",
        "git://github.com/acme/foo.git",
    ],
)
def test_urls_of_one_repository_share_an_identity(url):
    assert canonicalize(url) == "github.com/acme/foo"


def test_subgroups_are_kept():
    assert (
        canonicalize("git@gitlab.com:acme/team/foo.git") == "gitlab.com/acme/team/foo"
    )


def test_local_path_remote():
    assert canonicalize("/srv/git/foo.git") == "srv/git/foo"


def test_file_url():
    assert canonicalize("file:///srv/git/foo.git") == "srv/git/foo"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://github.com/",
        "git@github.com:",
        "weird::url",
        "transport::addr",
    ],
)
def test_unusable_urls_are_rejected(url):
    with pytest.raises(RemoteError):
        canonicalize(url)
