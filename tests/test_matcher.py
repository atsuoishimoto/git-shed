from __future__ import annotations

import pytest

from git_shed.matcher import matches


@pytest.mark.parametrize(
    "pattern,identity,expected",
    [
        ("github.com/acme/foo", "github.com/acme/foo", True),
        ("github.com/acme/foo", "github.com/acme/bar", False),
        ("github.com/acme/*", "github.com/acme/foo", True),
        ("github.com/acme/*", "github.com/acme/team/foo", False),
        ("github.com/*", "github.com/acme/foo", False),
        ("github.com/**", "github.com/acme/team/foo", True),
        ("gitlab.com/company/**", "gitlab.com/company", True),
        ("**", "github.com/acme/foo", True),
        ("*", "github.com/acme/foo", False),
        ("GitHub.com/Acme/*", "github.com/acme/foo", True),
        ("/github.com/acme/foo/", "github.com/acme/foo", True),
        ("", "github.com/acme/foo", False),
    ],
)
def test_matches(pattern, identity, expected):
    assert matches(pattern, identity) is expected
