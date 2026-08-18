from __future__ import annotations

import os
from pathlib import Path

import pytest

from git_shed import config as configlib
from git_shed.cli import main

CONFIG = """\
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "backend"
match = ["github.com/acme/api"]
"""


@pytest.fixture
def repo(make_repo, monkeypatch, home, config_file):
    root = make_repo()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(CONFIG, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def exclude_text(root: Path) -> str:
    return (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")


def test_sync_links_every_matching_shed(repo, home, capsys):
    assert main(["sync"]) == 0

    for name in ("company", "backend"):
        link = repo / ".shed" / name
        assert link.is_symlink()
        assert Path(os.readlink(link)) == home / ".git-shed" / "sheds" / name
        assert (home / ".git-shed" / "sheds" / name).is_dir()

    assert "/.shed/" in exclude_text(repo)
    out = capsys.readouterr().out
    assert out.startswith("Linked:\n")
    assert f"  .shed/backend -> {home / '.git-shed' / 'sheds' / 'backend'}" in out
    assert f"  .shed/company -> {home / '.git-shed' / 'sheds' / 'company'}" in out


def test_sync_is_idempotent(repo, capsys):
    main(["sync"])
    capsys.readouterr()
    assert main(["sync"]) == 0
    assert capsys.readouterr().out.strip() == "Already in sync."
    assert exclude_text(repo).count("/.shed/") == 1


def test_sync_drops_links_that_no_longer_match(repo, home, config_file, capsys):
    main(["sync"])
    config_file.write_text(
        '[[shed]]\nname = "company"\nmatch = ["github.com/acme/*"]\n', encoding="utf-8"
    )
    capsys.readouterr()

    assert main(["sync"]) == 0

    assert not (repo / ".shed" / "backend").exists()
    assert (home / ".git-shed" / "sheds" / "backend").is_dir()  # data survives
    assert "Unlinked:\n  .shed/backend\n" in capsys.readouterr().out


def test_sync_never_removes_real_directories(repo, capsys):
    (repo / ".shed").mkdir()
    keep = repo / ".shed" / "notes"
    keep.mkdir()
    (keep / "memo.md").write_text("hello", encoding="utf-8")

    assert main(["sync"]) == 0

    assert (keep / "memo.md").read_text(encoding="utf-8") == "hello"
    captured = capsys.readouterr()
    assert (
        "git shed: warning: .shed/notes is not a link, left untouched" in captured.err
    )
    assert "notes" not in captured.out


def test_sync_warns_when_a_shed_cannot_be_linked(repo, home, capsys):
    blocked = repo / ".shed" / "company"
    blocked.mkdir(parents=True)
    (blocked / "memo.md").write_text("hello", encoding="utf-8")

    assert main(["sync"]) == 0

    captured = capsys.readouterr()
    assert (blocked / "memo.md").read_text(encoding="utf-8") == "hello"
    assert (
        "git shed: warning: .shed/company is not a link, shed not linked"
        in captured.err
    )
    backend = home / ".git-shed" / "sheds" / "backend"
    assert f"Linked:\n  .shed/backend -> {backend}\n" in captured.out


def test_sync_repoints_a_link_to_the_conventional_path(repo, home, capsys):
    mountpoint = repo / ".shed"
    mountpoint.mkdir()
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    (mountpoint / "company").symlink_to(elsewhere, target_is_directory=True)
    capsys.readouterr()

    assert main(["sync"]) == 0

    company = home / ".git-shed" / "sheds" / "company"
    assert Path(os.readlink(mountpoint / "company")) == company
    assert elsewhere.is_dir()
    assert (
        f"Relinked:\n  .shed/company -> {home / '.git-shed' / 'sheds' / 'company'}\n"
        in capsys.readouterr().out
    )


def test_sync_without_matches_is_not_an_error(make_repo, home, monkeypatch, capsys):
    root = make_repo(name="other", url="git@github.com:someone/thing.git")
    monkeypatch.chdir(root)

    assert main(["sync", "--no-interactive"]) == 0

    assert not (root / ".shed").exists()
    assert "No shed matches:\n  github.com/someone/thing\n" in capsys.readouterr().out


def test_sync_outside_a_repository_fails(tmp_path, home, monkeypatch, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert main(["sync"]) == 1
    assert "not inside a Git repository" in capsys.readouterr().err


def test_sync_uses_shed_remote(repo, home, capsys):
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "upstream", "git@github.com:acme/worker.git"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "shed.remote", "upstream"], cwd=repo, check=True
    )

    assert main(["sync"]) == 0

    assert (repo / ".shed" / "company").is_symlink()
    assert not (repo / ".shed" / "backend").exists()


def test_status(repo, capsys):
    main(["sync"])
    capsys.readouterr()
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "repository:\n  github.com/acme/api  (origin)\n" in out
    assert "company  github.com/acme/*" in out
    assert ".shed/backend" in out


def test_status_reports_missing_mounts(repo, capsys):
    assert main(["status"]) == 0
    assert ".shed/company (missing)" in capsys.readouterr().out


def test_list_indents_the_patterns_under_each_shed(repo, capsys):
    assert main(["list"]) == 0

    assert capsys.readouterr().out == (
        "company\n  github.com/acme/*\nbackend\n  github.com/acme/api\n"
    )


def test_list_shows_every_pattern_not_only_the_matching_one(repo, config_file, capsys):
    config_file.write_text(
        '[[shed]]\nname = "company"\n'
        'match = ["github.com/acme/*", "github.com/me/*"]\n',
        encoding="utf-8",
    )

    assert main(["list"]) == 0

    assert capsys.readouterr().out == (
        "company\n  github.com/acme/*\n  github.com/me/*\n"
    )


def test_list_all_outside_a_repository(
    tmp_path, home, config_file, monkeypatch, capsys
):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(CONFIG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["list", "--all"]) == 0
    assert capsys.readouterr().out == (
        "company\n  github.com/acme/*\nbackend\n  github.com/acme/api\n"
    )


def test_path(repo, home, capsys):
    assert main(["path", "company"]) == 0
    company = home / ".git-shed" / "sheds" / "company"
    assert capsys.readouterr().out.strip() == str(company)


def test_path_of_an_unknown_shed(repo, capsys):
    assert main(["path", "nope"]) == 1
    assert "no shed named nope" in capsys.readouterr().err


def test_add_without_interaction(repo, config_file, capsys):
    assert main(["add", "extra", "github.com/acme/*", "x/y"]) == 0

    shed = configlib.load(config_file).get("extra")
    assert shed.match == ("github.com/acme/*", "x/y")


def test_add_needs_a_pattern_when_not_interactive(repo, capsys):
    assert main(["add", "extra"]) == 1
    assert "at least one match pattern is required" in capsys.readouterr().err


def test_add_extends_an_existing_shed(repo, config_file, capsys):
    assert main(["add", "company", "x/y"]) == 0

    assert configlib.load(config_file).get("company").match == (
        "github.com/acme/*",
        "x/y",
    )
    assert "Updated shed:\n  company\n" in capsys.readouterr().out


def test_add_of_a_pattern_that_is_already_there(repo, config_file, capsys):
    assert main(["add", "company", "github.com/acme/*"]) == 0

    assert configlib.load(config_file).get("company").match == ("github.com/acme/*",)
    assert "Already matched by shed:\n  company\n" in capsys.readouterr().out


def test_add_takes_any_number_of_patterns(repo, config_file):
    assert main(["add", "many", "a/b", "c/d", "e/f", "a/b"]) == 0

    assert configlib.load(config_file).get("many").match == ("a/b", "c/d", "e/f")


def test_remove_keeps_the_data(repo, home, capsys):
    main(["sync"])
    capsys.readouterr()

    assert main(["remove", "backend"]) == 0

    assert configlib.load(configlib.config_path()).get("backend") is None
    assert not (repo / ".shed" / "backend").exists()
    assert (home / ".git-shed" / "sheds" / "backend").is_dir()
    out = capsys.readouterr().out
    assert "Removed shed" in out and "Data kept at" in out


def test_no_command_prints_usage(capsys):
    assert main([]) == 0
    assert "usage: git shed" in capsys.readouterr().out


def test_sync_without_a_remote_matches_the_directory_name(
    make_repo, home, config_file, monkeypatch, capsys
):
    root = make_repo(name="solo", url=None)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '[[shed]]\nname = "notes"\nmatch = ["solo"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)

    assert main(["sync"]) == 0

    assert (root / ".shed" / "notes").is_symlink()
    notes = home / ".git-shed" / "sheds" / "notes"
    assert f"  .shed/notes -> {notes}" in capsys.readouterr().out


def test_status_without_a_remote(make_repo, home, config_file, monkeypatch, capsys):
    root = make_repo(name="solo", url=None)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '[[shed]]\nname = "notes"\nmatch = ["solo"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "repository:\n  solo  (no remote, using the directory name)\n" in out
    assert "notes  solo" in out


def test_sync_from_a_subdirectory_without_a_remote(
    make_repo, home, config_file, monkeypatch
):
    root = make_repo(name="solo", url=None)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '[[shed]]\nname = "notes"\nmatch = ["solo"]\n', encoding="utf-8"
    )
    inner = root / "src" / "deep"
    inner.mkdir(parents=True)
    monkeypatch.chdir(inner)

    assert main(["sync"]) == 0

    assert (root / ".shed" / "notes").is_symlink()


def test_a_configured_remote_that_does_not_exist_is_an_error(
    make_repo, home, monkeypatch, capsys
):
    import subprocess

    root = make_repo(name="solo", url=None)
    subprocess.run(
        ["git", "config", "--local", "shed.remote", "upstream"], cwd=root, check=True
    )
    monkeypatch.chdir(root)

    assert main(["sync"]) == 1
    assert "remote 'upstream' does not exist" in capsys.readouterr().err


def add_remote(root: Path, name: str, url: str) -> None:
    import subprocess

    subprocess.run(["git", "remote", "add", name, url], cwd=root, check=True)


def test_every_remote_contributes_an_identity(repo, home, config_file, capsys):
    config_file.write_text(
        CONFIG + '\n[[shed]]\nname = "fork"\nmatch = ["github.com/me/*"]\n',
        encoding="utf-8",
    )
    add_remote(repo, "fork", "git@github.com:me/api.git")

    assert main(["sync"]) == 0

    for name in ("company", "backend", "fork"):
        assert (repo / ".shed" / name).is_symlink()


def test_an_unusable_remote_url_is_a_warning(repo, home, capsys):
    add_remote(repo, "broken", "::::")

    assert main(["sync"]) == 0

    captured = capsys.readouterr()
    assert "git shed: warning: ignoring remote 'broken':" in captured.err
    assert (repo / ".shed" / "company").is_symlink()  # origin still counts


def test_only_unusable_remotes_falls_back_to_the_directory_name(
    make_repo, home, config_file, monkeypatch, capsys
):
    root = make_repo(name="solo", url="::::")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '[[shed]]\nname = "notes"\nmatch = ["solo"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)

    assert main(["sync"]) == 0

    captured = capsys.readouterr()
    assert "ignoring remote 'origin':" in captured.err
    assert (root / ".shed" / "notes").is_symlink()


def test_shed_remote_may_name_several_remotes(repo, home, config_file, capsys):
    import subprocess

    config_file.write_text(
        CONFIG + '\n[[shed]]\nname = "fork"\nmatch = ["github.com/me/*"]\n',
        encoding="utf-8",
    )
    add_remote(repo, "fork", "git@github.com:me/api.git")
    add_remote(repo, "other", "git@github.com:someone/api.git")
    for name in ("origin", "fork"):
        subprocess.run(
            ["git", "config", "--local", "--add", "shed.remote", name],
            cwd=repo,
            check=True,
        )

    assert main(["sync"]) == 0

    assert sorted(entry.name for entry in (repo / ".shed").iterdir()) == [
        "backend",
        "company",
        "fork",
    ]


def test_status_lists_every_remote(repo, capsys):
    add_remote(repo, "fork", "git@github.com:me/api.git")

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert (
        "repository:\n  github.com/acme/api  (origin)\n  github.com/me/api    (fork)\n"
        in out
    )


def test_sync_stores_sheds_under_the_override(repo, tmp_path, monkeypatch, capsys):
    root = tmp_path / "elsewhere"
    root.mkdir()
    (root / "config.toml").write_text(CONFIG, encoding="utf-8")
    monkeypatch.setenv("GIT_SHED_ROOT", str(root))

    assert main(["sync"]) == 0

    assert (root / "sheds" / "company").is_dir()
    assert Path(os.readlink(repo / ".shed" / "company")) == root / "sheds" / "company"
    assert f"  .shed/company -> {root / 'sheds' / 'company'}" in capsys.readouterr().out


def test_a_relative_override_is_an_error(repo, monkeypatch, capsys):
    monkeypatch.setenv("GIT_SHED_ROOT", "sheds")

    assert main(["sync"]) == 1
    assert "GIT_SHED_ROOT must be an absolute path" in capsys.readouterr().err


def test_a_closed_pipe_is_not_a_traceback(repo, monkeypatch, capsys):
    class ClosedPipe:
        def write(self, text):
            raise BrokenPipeError()

        def flush(self):
            pass

    monkeypatch.setattr("sys.stdout", ClosedPipe())

    assert main(["status"]) == 141


def test_remove_a_single_pattern(repo, config_file, capsys):
    main(["add", "company", "x/y"])
    capsys.readouterr()

    assert main(["remove", "company", "x/y"]) == 0

    assert configlib.load(config_file).get("company").match == ("github.com/acme/*",)
    assert "Updated shed:\n  company\n" in capsys.readouterr().out


def test_remove_several_patterns(repo, config_file, capsys):
    main(["add", "many", "a/b", "c/d", "e/f"])
    capsys.readouterr()

    assert main(["remove", "many", "a/b", "e/f"]) == 0

    assert configlib.load(config_file).get("many").match == ("c/d",)


def test_removing_the_last_pattern_keeps_the_shed(repo, config_file, capsys):
    assert main(["remove", "backend", "github.com/acme/api"]) == 0

    shed = configlib.load(config_file).get("backend")
    assert shed is not None
    assert shed.match == ()
    assert "No patterns left" in capsys.readouterr().out


def test_removing_an_unregistered_pattern_is_an_error(repo, config_file, capsys):
    assert main(["remove", "company", "nope/nope"]) == 1

    assert "has no pattern nope/nope" in capsys.readouterr().err
    assert configlib.load(config_file).get("company").match == ("github.com/acme/*",)


def test_removing_patterns_keeps_links_and_comments(repo, config_file, capsys):
    config_file.write_text(
        '# note\n[[shed]]\nname = "company"  # inline\n'
        'match = ["github.com/acme/*", "x/y"]\n',
        encoding="utf-8",
    )
    main(["sync"])
    capsys.readouterr()

    assert main(["remove", "company", "x/y"]) == 0

    text = config_file.read_text(encoding="utf-8")
    assert "# note" in text and "# inline" in text
    assert (repo / ".shed" / "company").is_symlink()
