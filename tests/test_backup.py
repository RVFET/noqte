from __future__ import annotations

import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

from noqte.backup import (
    create_local_backup,
    git_create_backup_branch,
    prune_backup_branches,
)
from noqte.config import BranchCleanupConfig, DotfileTarget
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


def test_prune_backup_branches_gfs(tmp_path: Path):
    repo_dir = tmp_path / "retention_repo"
    repo_dir.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@test.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo_dir, check=True)

    (repo_dir / "init.txt").write_text("baseline", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo_dir, check=True)

    fake_remote = tmp_path / "remote_retention.git"
    subprocess.run(["git", "init", "--bare", str(fake_remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(fake_remote)], cwd=repo_dir, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir, check=True, capture_output=True)

    now = datetime.now()

    ts_today_1 = (now - timedelta(minutes=15)).strftime("%d-%m-%Y_%H%M%S")
    ts_today_2 = (now - timedelta(minutes=5)).strftime("%d-%m-%Y_%H%M%S")

    day2 = now - timedelta(days=2)
    ts_day2_old = day2.replace(hour=10, minute=0, second=0).strftime("%d-%m-%Y_%H%M%S")
    ts_day2_new = day2.replace(hour=16, minute=0, second=0).strftime("%d-%m-%Y_%H%M%S")

    stale_day = now - timedelta(days=150)
    ts_stale = stale_day.strftime("%d-%m-%Y_%H%M%S")

    b_today_1 = f"backup-{ts_today_1}"
    b_today_2 = f"backup-{ts_today_2}"
    b_day2_old = f"backup-{ts_day2_old}"
    b_day2_new = f"backup-{ts_day2_new}"
    b_stale = f"backup-{ts_stale}"

    branches = [b_today_1, b_today_2, b_day2_old, b_day2_new, b_stale]
    for b in branches:
        subprocess.run(["git", "branch", b], cwd=repo_dir, check=True)
        subprocess.run(["git", "push", "origin", b], cwd=repo_dir, check=True, capture_output=True)

    config = BranchCleanupConfig(
        enabled=True,
        protect_today=True,
        retain_daily=7,
        retain_weekly=4,
        retain_monthly=3,
    )

    prune_backup_branches(repo_dir, config)

    res_local = subprocess.run(["git", "branch", "--list"], cwd=repo_dir, capture_output=True, text=True, check=True)
    local_branches = {line.strip().lstrip("* ") for line in res_local.stdout.splitlines()}

    assert b_today_1 in local_branches
    assert b_today_2 in local_branches
    assert b_day2_new in local_branches
    assert b_day2_old not in local_branches
    assert b_stale not in local_branches
    assert "main" in local_branches

    res_remote = subprocess.run(
        ["git", "ls-remote", "--heads", "origin"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    assert b_day2_old not in res_remote.stdout
    assert b_stale not in res_remote.stdout
    assert b_day2_new in res_remote.stdout
