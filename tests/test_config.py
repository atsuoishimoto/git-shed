from __future__ import annotations

import pytest

from git_shed import config as configlib
from git_shed.config import Shed
from git_shed.errors import ConfigError

SAMPLE = """\
# my sheds
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "backend"
match = [
  "github.com/acme/api",
  "github.com/acme/worker",
]
"""


def test_missing_file_is_an_empty_config(config_file):
    config = configlib.load(config_file)
    assert config.sheds == ()


def test_load(config_file):
    config_file.parent.mkdir(parents=True)
    config_file.write_text(SAMPLE, encoding="utf-8")

    config = configlib.load(config_file)
    assert [shed.name for shed in config.sheds] == ["company", "backend"]
    assert config.get("backend").match == (
        "github.com/acme/api",
        "github.com/acme/worker",
    )
    assert [shed.name for shed in config.matching(["github.com/acme/api"])] == [
        "company",
        "backend",
    ]
    assert config.matching(["github.com/other/api"]) == ()
    # A single identity may be passed as a plain string.
    assert [shed.name for shed in config.matching("github.com/acme/api")] == [
        "company",
        "backend",
    ]
    # A second identity brings in the sheds only it matches.
    assert config.matching(["github.com/me/fork"]) == ()
    assert [
        shed.name
        for shed in config.matching(["github.com/me/fork", "github.com/acme/api"])
    ] == ["company", "backend"]


@pytest.mark.parametrize(
    "text",
    [
        'shed = "company"',
        "[[shed]]\nmatch = []",
        '[[shed]]\nname = "a"\nmatch = 1',
        '[[shed]]\nname = "a/b"\nmatch = []',
        '[[shed]]\nname = "a"\n[[shed]]\nname = "a"',
        "[[shed]\nname =",
    ],
)
def test_invalid_config(config_file, text):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        configlib.load(config_file)


def test_append_creates_the_file(config_file):
    configlib.append_shed(config_file, Shed("company", ("github.com/acme/*",)))
    configlib.append_shed(config_file, Shed("backend", ("a/b", "c/d")))

    config = configlib.load(config_file)
    assert [shed.name for shed in config.sheds] == ["company", "backend"]
    assert config.get("backend").match == ("a/b", "c/d")


def test_remove_keeps_the_rest_of_the_file(config_file):
    config_file.parent.mkdir(parents=True)
    config_file.write_text(SAMPLE, encoding="utf-8")

    configlib.remove_shed(config_file, "company")

    text = config_file.read_text(encoding="utf-8")
    assert "# my sheds" in text
    assert "company" not in text
    assert [shed.name for shed in configlib.load(config_file).sheds] == ["backend"]


def test_remove_unknown_shed(config_file):
    config_file.parent.mkdir(parents=True)
    config_file.write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(ConfigError):
        configlib.remove_shed(config_file, "nope")


@pytest.mark.parametrize(
    "name",
    ["company", "a", "0x", "back-end", "a.b_c", "communications", "lpt10", "COM"],
)
def test_valid_names(name):
    assert configlib.validate_name(name) == name


def test_surrounding_whitespace_is_normalized():
    assert configlib.validate_name(" foo\n") == "foo"


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        ".",
        "..",
        ".hidden",
        "-x",
        "a/b",
        "a\\b",
        "a b",
        "fo\no",
        "foo#bar",
        "a:b",
        "a|b",
        "a*b",
        "a?b",
        'a"b',
        "a'b",
        "a;b",
        "a%b",
        "name.",
        "CON",
        "Com1",
        "LPT9",
        "nul.txt",
        "日本語",
        "x" * 65,
    ],
)
def test_invalid_names(name):
    with pytest.raises(ConfigError):
        configlib.validate_name(name)


def test_paths_follow_home(home, config_file):
    assert configlib.config_path() == config_file
    assert configlib.shed_path("company") == home / ".shed" / "company"


FORMATTED = """\
# my sheds
[[shed]]
name = "company"  # everything under the org
match = [
    'github.com/acme/*',
]

[[shed]]
name = "backend"
match = ["github.com/acme/api"]
"""


def test_editing_preserves_comments_and_formatting(config_file):
    config_file.parent.mkdir(parents=True)
    config_file.write_text(FORMATTED, encoding="utf-8")

    configlib.append_shed(config_file, Shed("extra", ("x/y",)))
    configlib.remove_shed(config_file, "backend")

    text = config_file.read_text(encoding="utf-8")
    assert "# my sheds" in text
    assert 'name = "company"  # everything under the org' in text
    assert "    'github.com/acme/*',\n" in text
    assert '\n[[shed]]\nname = "extra"' in text
    assert [shed.name for shed in configlib.load(config_file).sheds] == [
        "company",
        "extra",
    ]


def test_removing_the_last_shed_empties_the_file(config_file):
    configlib.append_shed(config_file, Shed("only", ("x/y",)))
    configlib.remove_shed(config_file, "only")

    assert configlib.load(config_file).sheds == ()
    assert config_file.read_text(encoding="utf-8").strip() == ""


def test_storage_root_defaults_to_home(home):
    assert configlib.storage_root() == home / ".shed"


def test_storage_root_override(home, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_SHED_ROOT", str(tmp_path / "elsewhere"))
    assert configlib.storage_root() == tmp_path / "elsewhere"
    assert configlib.shed_path("company") == tmp_path / "elsewhere" / "company"


def test_storage_root_override_expands_a_tilde(home, monkeypatch):
    monkeypatch.setenv("GIT_SHED_ROOT", "~/sheds")
    assert configlib.storage_root() == home / "sheds"


def test_a_blank_override_is_ignored(home, monkeypatch):
    monkeypatch.setenv("GIT_SHED_ROOT", "  ")
    assert configlib.storage_root() == home / ".shed"


@pytest.mark.parametrize("value", ["sheds", "./sheds", "../sheds"])
def test_a_relative_override_is_rejected(home, monkeypatch, value):
    monkeypatch.setenv("GIT_SHED_ROOT", value)
    with pytest.raises(ConfigError):
        configlib.storage_root()
