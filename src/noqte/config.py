from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def get_real_user_home() -> Path:
    """Resolve the real invoking user's home directory even when run under sudo."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and pwd:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError:
            pass
    return Path.home()


def resolve_path(path_val: str | Path) -> Path:
    """Expand user tilde without resolving symlinks away."""
    p_str = str(path_val)
    if p_str.startswith("~"):
        rel_part = p_str.lstrip("~").lstrip("/")
        return (get_real_user_home() / rel_part).resolve()
    return Path(p_str).resolve()


def get_current_platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    return sys.platform


class BranchCleanupConfig(BaseModel):
    enabled: bool = True
    protect_today: bool = True
    retain_daily: int = 7
    retain_weekly: int = 4
    retain_monthly: int = 12


class SettingsConfig(BaseModel):
    local_backups: bool = True
    git_backups: bool = True
    preflight: bool = True
    branch_cleanup: BranchCleanupConfig = Field(default_factory=BranchCleanupConfig)


class MacPackageSpec(BaseModel):
    name: str | None = None
    cask: bool = False


class PackageTarget(BaseModel):
    name: str
    manager: str = "pacman"
    os: list[str] = Field(default_factory=lambda: ["linux", "darwin"])
    mac: str | MacPackageSpec | None = None

    @field_validator("os", mode="before")
    @classmethod
    def coerce_os_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return list(v)

    def is_applicable(self, current_os: str) -> bool:
        if not self.os or "all" in self.os or "*" in self.os:
            return True
        allowed = [x.lower() for x in self.os]
        if current_os == "darwin" and ("darwin" in allowed or "mac" in allowed):
            return True
        return current_os in allowed


class DotfileTarget(BaseModel):
    name: str
    dest: str
    os: list[str] = Field(default_factory=lambda: ["linux", "darwin"])
    overwrite: bool = False
    exclude: list[str] | None = None
    include: list[str] | None = None
    temporarily_own: bool = True
    encrypted: bool = False

    @field_validator("os", mode="before")
    @classmethod
    def coerce_os_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return list(v)

    def is_applicable(self, current_os: str) -> bool:
        if not self.os or "all" in self.os or "*" in self.os:
            return True
        allowed = [x.lower() for x in self.os]
        if current_os == "darwin" and ("darwin" in allowed or "mac" in allowed):
            return True
        return current_os in allowed

    def resolve_destination(self) -> Path:
        return resolve_path(self.dest)


class NoqteConfig(BaseModel):
    repo_path: str = "~/dotfiles"
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    packages: list[PackageTarget] = Field(default_factory=list)
    configs: list[DotfileTarget] = Field(default_factory=list)

    def get_repo_dir(self) -> Path:
        return resolve_path(self.repo_path)

    def get_configs_dir(self) -> Path:
        return self.get_repo_dir() / "configs"


def find_config_file(custom_path: Path | None = None) -> Path:
    """Resolve noqte.yaml path from CLI argument, env var, CWD, or ~/.config/noqte/."""
    if custom_path:
        p = custom_path.resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"Specified configuration file missing: {custom_path}")

    env_val = os.environ.get("NOQTE_CONFIG")
    if env_val:
        p = Path(env_val).resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"NOQTE_CONFIG path missing: {env_val}")

    candidates = [
        Path.cwd() / "noqte.yaml",
        Path.cwd() / "noqte.yml",
        Path.cwd() / ".noqte.yaml",
        Path.home() / ".config" / "noqte" / "noqte.yaml",
        Path.home() / ".config" / "noqte" / "config.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()

    raise FileNotFoundError(
        "Could not find noqte.yaml in current directory or ~/.config/noqte/. Specify location using --config <path>."
    )


def load_config(custom_path: Path | None = None) -> tuple[NoqteConfig, Path]:
    cfg_path = find_config_file(custom_path)
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Root node of {cfg_path.name} must be a dictionary.")

    return NoqteConfig.model_validate(data), cfg_path
