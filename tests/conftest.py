from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SUDO_USER", raising=False)
    return home


@pytest.fixture
def sample_config_path(tmp_path: Path, fake_home: Path) -> Path:
    repo_dir = tmp_path / "repo"
    configs_dir = repo_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    # Populate dummy files so to-host has files to transfer
    (configs_dir / ".zshrc").write_text("# dummy zshrc", encoding="utf-8")
    (configs_dir / "app").mkdir(parents=True, exist_ok=True)
    (configs_dir / "app" / "config.json").write_text("{}", encoding="utf-8")

    config_data = {
        "repo_path": str(repo_dir),
        "settings": {
            "local_backups": True,
            "git_backups": False,
            "preflight": False,
        },
        "packages": [
            {"name": "ripgrep"},
            {"name": "ghostty", "mac": {"cask": True}},
        ],
        "configs": [
            {"name": ".zshrc", "dest": "~/test_zshrc"},
            {"name": "app/config.json", "dest": "~/.config/app/config.json"},
        ],
    }

    cfg_file = repo_dir / "noqte.yaml"
    cfg_file.write_text(yaml.safe_dump(config_data), encoding="utf-8")
    return cfg_file
