from __future__ import annotations

import pytest

from git_shed import config as configlib
from git_shed import prompt
from git_shed.cli import main


@pytest.fixture
def answers(monkeypatch):
    """Make the process look interactive and feed canned answers to input()."""

    def _answers(*values):
        pending = list(values)
        monkeypatch.setattr(prompt, "interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt_text="": pending.pop(0))
        return pending

    return _answers


def test_sync_offers_to_create_a_shed(make_repo, home, monkeypatch, answers, capsys):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    # create? / name / pattern / confirm
    answers("y", "company", "github.com/acme/*", "y")

    assert main(["sync"]) == 0

    shed = configlib.load(configlib.config_path()).get("company")
    assert shed.match == ("github.com/acme/*",)
    assert (root / ".shed" / "company").is_symlink()
    assert (home / ".git-shed" / "sheds" / "company").is_dir()
    out = capsys.readouterr().out
    assert out.endswith(
        "Created shed:\n  company\n"
        f"\nLinked:\n  .shed/company -> {home / '.git-shed' / 'sheds' / 'company'}\n"
    )


def test_sync_accepts_the_defaults(make_repo, home, monkeypatch, answers):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    answers("", "", "", "y")

    assert main(["sync"]) == 0

    shed = configlib.load(configlib.config_path()).get("foo")
    assert shed.match == ("github.com/acme/foo",)
    assert (root / ".shed" / "foo").is_symlink()


def test_declining_creates_nothing(make_repo, home, monkeypatch, answers):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    answers("n")

    assert main(["sync"]) == 0

    assert configlib.load(configlib.config_path()).sheds == ()
    assert not (root / ".shed").exists()


def test_declining_the_confirmation_creates_nothing(
    make_repo, home, monkeypatch, answers
):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    answers("y", "company", "github.com/acme/*", "n")

    assert main(["sync"]) == 0

    assert configlib.load(configlib.config_path()).sheds == ()


def test_add_asks_for_one_pattern(make_repo, home, monkeypatch, answers):
    root = make_repo(url="git@github.com:acme/api.git")
    monkeypatch.chdir(root)
    # name / pattern / confirm -- no "add another?" round
    answers("backend", "github.com/acme/api", "y")

    assert main(["add"]) == 0

    shed = configlib.load(configlib.config_path()).get("backend")
    assert shed.match == ("github.com/acme/api",)


def test_the_confirmation_shows_the_values_and_needs_a_yes_or_no(
    make_repo, home, monkeypatch, answers, capsys
):
    root = make_repo(url="git@github.com:acme/api.git")
    monkeypatch.chdir(root)
    # name / pattern / an unusable answer / confirm
    answers("backend", "github.com/acme/api", "maybe", "y")

    assert main(["add"]) == 0

    out = capsys.readouterr().out
    assert (
        "Create shed:\n  name:  backend\n  match:\n    - github.com/acme/api\n" in out
    )
    assert "Please answer 'y' or 'n'." in out


def test_add_extends_an_existing_shed_interactively(
    make_repo, home, monkeypatch, answers, config_file, capsys
):
    root = make_repo(url="git@github.com:acme/api.git")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '[[shed]]\nname = "company"\nmatch = ["github.com/acme/*"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    # name / pattern / confirm
    answers("company", "github.com/other/*", "y")

    assert main(["add"]) == 0

    assert configlib.load(config_file).get("company").match == (
        "github.com/acme/*",
        "github.com/other/*",
    )
    out = capsys.readouterr().out
    assert "Add to shed:" in out
    assert "Updated shed:\n  company\n" in out


def test_declining_the_confirmation_of_add(make_repo, home, monkeypatch, answers):
    root = make_repo(url="git@github.com:acme/api.git")
    monkeypatch.chdir(root)
    answers("backend", "github.com/acme/api", "n")

    assert main(["add"]) == 1

    assert configlib.load(configlib.config_path()).sheds == ()


def test_no_interactive_skips_the_prompt(make_repo, home, monkeypatch, answers, capsys):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    answers("y", "company")

    assert main(["sync", "--no-interactive"]) == 0

    assert configlib.load(configlib.config_path()).sheds == ()
    assert "No shed matches:\n  github.com/acme/foo\n" in capsys.readouterr().out


def test_existing_shed_data_is_pointed_out(
    make_repo, home, monkeypatch, answers, capsys
):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    existing = home / ".git-shed" / "sheds" / "company"
    existing.mkdir(parents=True)
    (existing / "notes.md").write_text("kept", encoding="utf-8")
    answers("y", "company", "github.com/acme/*", "y")

    assert main(["sync"]) == 0

    out = capsys.readouterr().out
    assert f"  path:  {existing}  (exists; its contents are kept)" in out
    assert (existing / "notes.md").read_text(encoding="utf-8") == "kept"


def test_a_new_path_is_shown_without_a_note(
    make_repo, home, monkeypatch, answers, capsys
):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    answers("y", "company", "github.com/acme/*", "y")

    assert main(["sync"]) == 0

    company = home / ".git-shed" / "sheds" / "company"
    assert f"  path:  {company}\n" in capsys.readouterr().out


def test_a_file_in_the_way_is_pointed_out(
    make_repo, home, monkeypatch, answers, capsys
):
    root = make_repo(url="git@github.com:acme/foo.git")
    monkeypatch.chdir(root)
    (home / ".git-shed" / "sheds").mkdir(parents=True)
    (home / ".git-shed" / "sheds" / "company").write_text(
        "not a directory", encoding="utf-8"
    )
    answers("y", "company", "github.com/acme/*", "n")

    assert main(["sync"]) == 0

    assert "(exists but is not a directory)" in capsys.readouterr().out


def test_defaults_without_a_remote_come_from_the_directory(
    make_repo, home, monkeypatch, answers, capsys
):
    root = make_repo(name="solo", url=None)
    monkeypatch.chdir(root)
    # create? / name (default) / pattern (default) / confirm
    answers("y", "", "", "y")

    assert main(["sync"]) == 0

    shed = configlib.load(configlib.config_path()).get("solo")
    assert shed.match == ("solo",)
    assert (root / ".shed" / "solo").is_symlink()
