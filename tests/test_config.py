from __future__ import annotations

from pathlib import Path

import pytest

from noqte.config import (
    DotfileTarget,
    NoqteConfig,
    find_config_file,
    load_config,
    resolve_path,
)


def test_config_model_validation():
    data = {
        "repo_path": "~/dotfiles",
        "settings": {
            "local_backups": False,
            "git_backups": True,
            "preflight": False,
            "branch_cleanup": {
                "enabled": True,
                "protect_today": True,
                "retain_daily": 5,
                "retain_weekly": 3,
                "retain_monthly": 6,
            },
        },
        "packages": [{"name": "ripgrep", "os": "linux"}],
        "configs": [{"name": ".zshrc", "dest": "~/.zshrc", "os": "darwin"}],
    }
    cfg = NoqteConfig.model_validate(data)
    assert cfg.settings.local_backups is False
    assert cfg.settings.git_backups is True
    assert cfg.settings.branch_cleanup.retain_daily == 5
    assert cfg.settings.branch_cleanup.retain_weekly == 3
    assert cfg.settings.branch_cleanup.retain_monthly == 6
    assert cfg.packages[0].os == ["linux"]
    assert cfg.configs[0].os == ["darwin"]


def test_os_coercion_from_string():
    target = DotfileTarget(name=".bashrc", dest="~/.bashrc", os="linux")
    assert target.os == ["linux"]
    assert target.is_applicable("linux") is True
    assert target.is_applicable("darwin") is False


def test_resolve_path_expansion(fake_home: Path):
    resolved = resolve_path("~/my_file.txt")
    assert resolved == fake_home / "my_file.txt"


def test_find_config_file_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom = tmp_path / "custom.yaml"
    custom.touch()
    assert find_config_file(custom) == custom.resolve()

    env_cfg = tmp_path / "env.yaml"
    env_cfg.touch()
    monkeypatch.setenv("NOQTE_CONFIG", str(env_cfg))
    assert find_config_file() == env_cfg.resolve()

    monkeypatch.delenv("NOQTE_CONFIG")
    monkeypatch.chdir(tmp_path)
    cwd_cfg = tmp_path / "noqte.yaml"
    cwd_cfg.touch()
    assert find_config_file() == cwd_cfg.resolve()


def test_load_config_valid(sample_config_path: Path):
    cfg, path = load_config(sample_config_path)
    assert path == sample_config_path
    assert len(cfg.configs) == 2
    assert len(cfg.packages) == 2


def test_dotfile_target_ignore_diff():
    target_default = DotfileTarget(name=".bashrc", dest="~/.bashrc")
    assert target_default.ignore_diff is False

    target_ignored = DotfileTarget(name=".bashrc", dest="~/.bashrc", ignore_diff=True)
    assert target_ignored.ignore_diff is True
