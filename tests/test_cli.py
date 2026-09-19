from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from noqte.cli import app

runner = CliRunner()


def test_cli_help():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "Fast, modular, cross-platform dotfiles and package manager" in res.stdout


def test_cli_configs_help():
    res = runner.invoke(app, ["configs", "--help"])
    assert res.exit_code == 0
    assert "to-host" in res.stdout
    assert "from-host" in res.stdout
    assert "clear" in res.stdout


def test_cli_pkgs_help():
    res = runner.invoke(app, ["pkgs", "--help"])
    assert res.exit_code == 0
    assert "install" in res.stdout


def test_cli_dry_run(sample_config_path: Path):
    res_configs = runner.invoke(
        app,
        ["configs", "to-host", "--config", str(sample_config_path), "--dry-run"],
    )
    assert res_configs.exit_code == 0
    assert "[DRY-RUN]" in res_configs.stdout

    res_pkgs = runner.invoke(
        app,
        ["pkgs", "install", "--config", str(sample_config_path), "--dry-run"],
    )
    assert res_pkgs.exit_code == 0
    assert "Package Installation Audit (Dry-Run)" in res_pkgs.stdout


def test_cli_pkgs_install_manager_filter(sample_config_path: Path):
    from noqte.config import get_current_platform

    current_os = get_current_platform()
    target_mgr = "brew" if current_os == "darwin" else "pacman"

    res = runner.invoke(
        app,
        ["pkgs", "install", "--config", str(sample_config_path), "--dry-run", "-m", target_mgr],
    )
    assert res.exit_code == 0
    assert f"({target_mgr} only)" in res.stdout

    res_unconfigured = runner.invoke(
        app,
        ["pkgs", "install", "--config", str(sample_config_path), "--dry-run", "-m", "flatpak"],
    )
    assert res_unconfigured.exit_code == 0
    assert "Requested manager not present in config" in res_unconfigured.stdout
    assert "No matching configured managers found" in res_unconfigured.stdout
