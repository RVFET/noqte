from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Annotated

import typer

from noqte.backup import create_local_backup, git_create_backup_branch
from noqte.config import get_current_platform, load_config
from noqte.crypt import PassphraseSession
from noqte.file_actions import (
    collect_target,
    deploy_target,
    get_repo_target_path,
    is_symlink_safeguard,
    prune_empty_directories,
)
from noqte.logger import console, log_error, log_info, log_step
from noqte.managers import execute_package_pipeline

app = typer.Typer(
    name="noqte",
    help="Fast, modular, cross-platform dotfiles and package manager.",
    no_args_is_help=True,
)
configs_app = typer.Typer(help="Manage dotfile transfers between host and repository.")
pkgs_app = typer.Typer(help="Manage system and release package installations.")

app.add_typer(configs_app, name="configs")
app.add_typer(pkgs_app, name="pkgs")


@configs_app.command("to-host")
def configs_to_host(
    config_file: Annotated[Path | None, typer.Option("--config", "-c", help="Path to noqte.yaml")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulate transfer without modifying filesystem")] = False,
    no_local_backup: Annotated[bool, typer.Option("--no-local-backup", help="Disable local backup archive creation")] = False,
    no_git_backup: Annotated[bool, typer.Option("--no-git-backup", help="Disable Git snapshot branch creation")] = False,
) -> None:
    """Deploy repository configs to host system."""
    config, _ = load_config(config_file)
    current_os = get_current_platform()
    configs_dir = config.get_configs_dir()
    repo_dir = config.get_repo_dir()

    log_step(f"Deploying configs: {configs_dir} -> Host ({current_os})")
    applicable = [c for c in config.configs if c.is_applicable(current_os)]

    session = PassphraseSession()
    if any(c.encrypted for c in applicable) and not dry_run:
        session.get_decryption_passphrase()

    should_local_backup = config.settings.local_backups and not no_local_backup and not dry_run
    should_git_backup = config.settings.git_backups and not no_git_backup and not dry_run

    if should_local_backup:
        host_paths = [c.resolve_destination() for c in applicable]
        create_local_backup(host_paths, prefix="to_host_local")

    if should_git_backup:
        git_create_backup_branch(
            repo_dir,
            configs_dir,
            applicable,
            current_os,
            session,
            cleanup_config=config.settings.branch_cleanup,
        )

    start = time.perf_counter()
    for entry in applicable:
        deploy_target(entry, configs_dir, session, dry_run=dry_run)

    elapsed = time.perf_counter() - start
    console.print(f"\nto-host completed in {elapsed:.3f}s.")


@configs_app.command("from-host")
def configs_from_host(
    config_file: Annotated[Path | None, typer.Option("--config", "-c", help="Path to noqte.yaml")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulate collection without modifying repository")] = False,
    no_local_backup: Annotated[bool, typer.Option("--no-local-backup", help="Disable local backup archive creation")] = False,
) -> None:
    """Collect host configurations into the repository."""
    config, _ = load_config(config_file)
    current_os = get_current_platform()
    configs_dir = config.get_configs_dir()

    log_step(f"Collecting configs: Host -> {configs_dir}")
    applicable = [c for c in config.configs if c.is_applicable(current_os)]

    session = PassphraseSession()
    if any(c.encrypted for c in applicable) and not dry_run:
        session.get_encryption_passphrase()

    should_local_backup = config.settings.local_backups and not no_local_backup and not dry_run
    if should_local_backup:
        repo_paths = [get_repo_target_path(configs_dir, c) for c in applicable]
        create_local_backup(repo_paths, prefix="from_host_local")

    if not dry_run:
        configs_dir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    for entry in applicable:
        collect_target(entry, configs_dir, session, dry_run=dry_run)

    elapsed = time.perf_counter() - start
    console.print(f"\nfrom-host completed in {elapsed:.3f}s.")


@configs_app.command("clear")
def configs_clear(
    config_file: Annotated[Path | None, typer.Option("--config", "-c", help="Path to noqte.yaml")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulate clear without deleting files")] = False,
    no_local_backup: Annotated[bool, typer.Option("--no-local-backup", help="Disable local backup archive creation")] = False,
) -> None:
    """Purge managed configurations from the local repository directory."""
    config, _ = load_config(config_file)
    current_os = get_current_platform()
    configs_dir = config.get_configs_dir()

    log_step(f"Clearing tracked configs inside: {configs_dir}")
    applicable = [c for c in config.configs if c.is_applicable(current_os)]

    should_local_backup = config.settings.local_backups and not no_local_backup and not dry_run
    if should_local_backup:
        repo_paths = [get_repo_target_path(configs_dir, c) for c in applicable]
        create_local_backup(repo_paths, prefix="clear_local")

    for entry in applicable:
        targets_to_remove = [get_repo_target_path(configs_dir, entry)]
        if entry.encrypted:
            targets_to_remove.append(configs_dir / entry.name)

        for target in targets_to_remove:
            if is_symlink_safeguard(target, "clear target"):
                continue

            if target.exists():
                if dry_run:
                    log_info(f"[DRY-RUN] remove: {target}")
                    continue
                try:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    log_info(f"Removed: '{target.name}' from repository configs.")
                except Exception as e:
                    log_error(f"Failed removing '{target.name}': {e}")

    pruned = prune_empty_directories(configs_dir, dry_run=dry_run)
    for p in pruned:
        rel = p.relative_to(configs_dir)
        if dry_run:
            log_info(f"[DRY-RUN] prune empty folder: {rel}")
        else:
            log_info(f"Pruned empty folder: {rel}")


@pkgs_app.command("install")
def pkgs_install(
    config_file: Annotated[Path | None, typer.Option("--config", "-c", help="Path to noqte.yaml")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Audit packages and show commands without modifying system")
    ] = False,
    manager: Annotated[
        list[str] | None, typer.Option("--manager", "-m", help="Filter execution to specific package manager(s)")
    ] = None,
    no_preflight: Annotated[bool, typer.Option("--no-preflight", help="Skip package manager preflight upgrades")] = False,
) -> None:
    """Audit and install missing packages across all configured managers."""
    config, _ = load_config(config_file)
    current_os = get_current_platform()

    run_preflight = config.settings.preflight and not no_preflight
    execute_package_pipeline(
        config=config,
        current_os=current_os,
        preflight=run_preflight,
        dry_run=dry_run,
        selected_managers=manager,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
