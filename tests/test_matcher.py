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
        ("github.com/acme-*/api", "github.com/acme-jp/api", True),
        ("github.com/acme-*/api", "github.com/acme/api", False),
        ("github.com/acme/repo_*", "github.com/acme/repo_foo", True),
        ("github.com/acme/repo_*", "github.com/acme/other", False),
        ("*/acme/*", "github.com/acme/foo", True),
        ("*/acme/*", "gitlab.com/acme/foo", True),
        ("*/acme/*", "github.com/other/foo", False),
        ("github.com/a*e/foo", "github.com/acme/foo", True),
        ("GitHub.com/Acme/*", "github.com/acme/foo", True),
        ("/github.com/acme/foo/", "github.com/acme/foo", True),
        ("", "github.com/acme/foo", False),
    ],
)
def test_matches(pattern, identity, expected):
    assert matches(pattern, identity) is expected
