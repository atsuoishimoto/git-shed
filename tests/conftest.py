from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated HOME so that ~/.git-shed is per-test."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("GIT_SHED_ROOT", raising=False)
    return home


@pytest.fixture
def config_file(home):
    return home / ".git-shed" / "config.toml"


def write_config(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def make_repo(tmp_path):
    """Create a Git repository, with the given remote URL unless it is None."""

    def _make(
        name: str = "repo", url: str | None = "git@github.com:acme/api.git"
    ) -> Path:
        root = tmp_path / name
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        if url is not None:
            subprocess.run(
                ["git", "remote", "add", "origin", url], cwd=root, check=True
            )
        return root

    return _make
