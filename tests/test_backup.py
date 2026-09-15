from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

from noqte.backup import create_local_backup, git_create_backup_branch
from noqte.config import DotfileTarget
from noqte.crypt import PassphraseSession


def test_create_local_backup(tmp_path: Path, fake_home: Path):
    p1 = fake_home / "test1.txt"
    p1.write_text("content 1", encoding="utf-8")

    archive = create_local_backup([p1], prefix="unit_test")
    assert archive is not None
    assert archive.exists()

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        assert any("test1.txt" in n for n in names)


def test_git_snapshot_with_diff(tmp_path: Path, fake_home: Path, monkeypatch):
    monkeypatch.setenv("NOQTE_PASSPHRASE", "pass")
    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir()
    configs_dir = repo_dir / "configs"
    configs_dir.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@test.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo_dir, check=True)

    readme = repo_dir / "README.md"
    readme.write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)

    fake_remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(fake_remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(fake_remote)], cwd=repo_dir, check=True)

    host_file = fake_home / ".tmux.conf"
    host_file.write_text("set -g mouse on", encoding="utf-8")

    entry = DotfileTarget(name=".tmux.conf", dest="~/.tmux.conf")
    session = PassphraseSession()

    git_create_backup_branch(repo_dir, configs_dir, [entry], current_os="linux", session=session)

    res = subprocess.run(["git", "ls-remote", "--heads", "origin"], cwd=repo_dir, capture_output=True, text=True)
    assert "backup-" in res.stdout
