from __future__ import annotations

import os
from pathlib import Path

import pytest

from git_shed import links as linkslib
from git_shed.cli import main

CONFIG = """\
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "scratch"
match = ["github.com/nobody/*"]
"""


@pytest.fixture
def repo(make_repo, monkeypatch, home, config_file):
    root = make_repo()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(CONFIG, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def listed(root: Path) -> tuple[str, ...]:
    return linkslib.read(root / ".shed")


def test_link_adds_an_entry_and_the_link(repo, home, capsys):
    assert main(["link", "scratch"]) == 0

    link = repo / ".shed" / "scratch"
    assert Path(os.readlink(link)) == home / ".git-shed" / "sheds" / "scratch"
    assert listed(repo) == ("scratch",)
    assert (repo / ".shed" / ".sheds").read_text(encoding="utf-8") == "scratch\n"
    scratch = home / ".git-shed" / "sheds" / "scratch"
    assert f"  .shed/scratch -> {scratch}" in capsys.readouterr().out


def test_sync_keeps_an_explicit_link(repo, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["sync"]) == 0

    assert (repo / ".shed" / "scratch").is_symlink()
    assert (repo / ".shed" / "company").is_symlink()
    assert listed(repo) == ("scratch",)


def test_sync_restores_a_link_removed_by_hand(repo):
    main(["link", "scratch"])
    (repo / ".shed" / "scratch").unlink()

    assert main(["sync"]) == 0

    assert (repo / ".shed" / "scratch").is_symlink()


def test_sync_does_not_warn_about_the_list_file(repo, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["sync"]) == 0

    assert ".sheds" not in capsys.readouterr().err


def test_linking_twice_is_a_no_op(repo, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["link", "scratch"]) == 0

    out = capsys.readouterr().out
    assert ".shed/scratch is already linked" in out
    assert listed(repo) == ("scratch",)


def test_unlink_drops_the_entry_and_the_link(repo, home, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["unlink", "scratch"]) == 0

    assert not (repo / ".shed" / "scratch").exists()
    assert not (repo / ".shed" / ".sheds").exists()
    assert (home / ".git-shed" / "sheds" / "scratch").is_dir()  # data survives
    assert "Unlinked:\n  .shed/scratch\n" in capsys.readouterr().out


def test_unlink_of_a_matched_shed_is_refused(repo, capsys):
    main(["sync"])
    capsys.readouterr()

    assert main(["unlink", "company"]) == 1

    assert (repo / ".shed" / "company").is_symlink()
    assert "comes from the configuration" in capsys.readouterr().err


def test_unlink_of_something_not_linked(repo, capsys):
    assert main(["unlink", "scratch"]) == 1
    assert "is not linked" in capsys.readouterr().err


def test_unlink_warns_when_the_shed_still_matches(repo, capsys):
    main(["link", "company"])
    capsys.readouterr()

    assert main(["unlink", "company"]) == 0

    assert (
        "matches this repository; the next sync links it again"
        in capsys.readouterr().err
    )


def test_link_of_an_unknown_shed(repo, capsys):
    assert main(["link", "nope"]) == 1
    assert "no shed named nope" in capsys.readouterr().err
    assert not (repo / ".shed").exists()


def test_an_unknown_entry_is_reported_and_kept(repo, capsys):
    mountpoint = repo / ".shed"
    mountpoint.mkdir()
    (mountpoint / ".sheds").write_text("gone\n", encoding="utf-8")

    assert main(["sync"]) == 0

    captured = capsys.readouterr()
    assert "unknown shed 'gone' in .shed/.sheds" in captured.err
    assert (mountpoint / ".sheds").read_text(encoding="utf-8") == "gone\n"


def test_status_marks_explicit_links(repo, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "scratch  (linked)" in out
    assert "company  github.com/acme/*" in out
    assert ".shed/scratch" in out
    assert ".sheds" not in out


def test_remove_drops_the_entry_too(repo, capsys):
    main(["link", "scratch"])
    capsys.readouterr()

    assert main(["remove", "scratch"]) == 0

    assert listed(repo) == ()
    assert not (repo / ".shed" / "scratch").exists()


def test_comments_and_blanks_are_ignored(repo):
    mountpoint = repo / ".shed"
    mountpoint.mkdir()
    (mountpoint / ".sheds").write_text(
        "# extras\n\nscratch  # for the audit\n", encoding="utf-8"
    )

    assert linkslib.read(mountpoint) == ("scratch",)

    assert main(["sync"]) == 0

    assert (mountpoint / "scratch").is_symlink()


def test_link_accepts_an_undefined_shed_that_exists(repo, home, capsys):
    existing = home / ".git-shed" / "sheds" / "loose"
    existing.mkdir(parents=True)
    (existing / "notes.md").write_text("kept", encoding="utf-8")

    assert main(["link", "loose"]) == 0

    assert Path(os.readlink(repo / ".shed" / "loose")) == existing
    assert listed(repo) == ("loose",)
    assert (existing / "notes.md").read_text(encoding="utf-8") == "kept"


def test_sync_keeps_a_link_to_an_undefined_shed(repo, home, capsys):
    (home / ".git-shed" / "sheds" / "loose").mkdir(parents=True)
    main(["link", "loose"])
    capsys.readouterr()

    assert main(["sync"]) == 0

    assert (repo / ".shed" / "loose").is_symlink()
    assert capsys.readouterr().err == ""


def test_link_refuses_a_name_with_neither_definition_nor_directory(repo, capsys):
    assert main(["link", "loose"]) == 1

    err = capsys.readouterr().err
    assert "no shed named loose" in err
    assert "does not exist" in err
    assert not (repo / ".shed").exists()


def test_status_shows_an_undefined_linked_shed(repo, home, capsys):
    (home / ".git-shed" / "sheds" / "loose").mkdir(parents=True)
    main(["link", "loose"])
    capsys.readouterr()

    assert main(["status"]) == 0

    assert "loose    (linked)" in capsys.readouterr().out


def test_path_of_an_undefined_shed_that_exists(repo, home, capsys):
    (home / ".git-shed" / "sheds" / "loose").mkdir(parents=True)

    assert main(["path", "loose"]) == 0

    loose = home / ".git-shed" / "sheds" / "loose"
    assert capsys.readouterr().out.strip() == str(loose)
