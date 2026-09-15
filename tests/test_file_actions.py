from __future__ import annotations

from pathlib import Path

from noqte.config import DotfileTarget
from noqte.crypt import PassphraseSession
from noqte.file_actions import (
    build_allowed_paths,
    collect_target,
    deploy_target,
    prune_empty_directories,
    safe_copy_file,
)


def test_safe_copy_file_preserves_mode(tmp_path: Path):
    src = tmp_path / "src.txt"
    dest = tmp_path / "dest.txt"

    src.write_text("hello updated", encoding="utf-8")
    dest.write_text("old content", encoding="utf-8")
    dest.chmod(0o444)

    safe_copy_file(src, dest, temporarily_own=True)

    assert dest.read_text(encoding="utf-8") == "hello updated"
    assert dest.stat().st_mode & 0o777 == 0o444


def test_build_allowed_paths_glob_filtering(tmp_path: Path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").touch()
    (tree / "b.txt").touch()
    (tree / "sub").mkdir()
    (tree / "sub" / "c.json").touch()
    (tree / "sub" / "d.log").touch()

    allowed = build_allowed_paths(tree, exclude_patterns=None, include_patterns=["**/*.json"])
    assert allowed is not None

    allowed_posix = {p.as_posix() for p in allowed}
    assert "a.json" in allowed_posix
    assert "sub/c.json" in allowed_posix
    assert "b.txt" not in allowed_posix
    assert "sub/d.log" not in allowed_posix


def test_prune_empty_directories(tmp_path: Path):
    base = tmp_path / "configs"
    empty_nested = base / "a" / "b" / "c"
    empty_nested.mkdir(parents=True)

    kept_dir = base / "keep"
    kept_dir.mkdir(parents=True)
    (kept_dir / "file.txt").touch()

    _pruned = prune_empty_directories(base)
    assert not (base / "a").exists()
    assert kept_dir.exists()
    assert (kept_dir / "file.txt").exists()


def test_collect_and_deploy_plain(tmp_path: Path, fake_home: Path):
    configs_dir = tmp_path / "repo" / "configs"
    configs_dir.mkdir(parents=True)

    host_file = fake_home / ".zshrc"
    host_file.write_text("export TEST=1", encoding="utf-8")

    entry = DotfileTarget(name=".zshrc", dest="~/.zshrc")
    session = PassphraseSession()

    assert collect_target(entry, configs_dir, session) is True
    assert (configs_dir / ".zshrc").read_text(encoding="utf-8") == "export TEST=1"

    host_file.unlink()
    assert deploy_target(entry, configs_dir, session) is True
    assert host_file.read_text(encoding="utf-8") == "export TEST=1"


def test_collect_and_deploy_encrypted(tmp_path: Path, fake_home: Path, monkeypatch):
    monkeypatch.setenv("NOQTE_PASSPHRASE", "test-passphrase")
    configs_dir = tmp_path / "repo" / "configs"
    configs_dir.mkdir(parents=True)

    host_file = fake_home / ".zshenv"
    host_file.write_text("SECRET_KEY=12345", encoding="utf-8")

    entry = DotfileTarget(name=".zshenv", dest="~/.zshenv", encrypted=True)
    session = PassphraseSession()

    assert collect_target(entry, configs_dir, session) is True
    encrypted_path = configs_dir / ".zshenv.encrypted"
    assert encrypted_path.exists()
    assert encrypted_path.read_bytes() != b"SECRET_KEY=12345"

    host_file.unlink()
    assert deploy_target(entry, configs_dir, session) is True
    assert host_file.read_text(encoding="utf-8") == "SECRET_KEY=12345"
