from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

import typer

from noqte.config import DotfileTarget, get_real_user_home
from noqte.crypt import PassphraseSession
from noqte.file_actions import collect_target, is_symlink_safeguard
from noqte.logger import console, log_error, log_info, log_warn


def create_local_backup(paths: list[Path], prefix: str) -> Path | None:
    existing = [p for p in paths if not is_symlink_safeguard(p, "backup target") and p.exists()]
    if not existing:
        return None

    backup_dir = get_real_user_home() / ".dotfiles-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%d-%m-%Y_%H%M%S")
    archive_path = backup_dir / f"{prefix}_{timestamp}.tar.gz"
    real_home = get_real_user_home()

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for p in existing:
                try:
                    rel_path = p.relative_to(real_home)
                    arcname = Path("HOME") / rel_path
                except ValueError:
                    arcname = Path("ROOT") / p.relative_to(Path("/"))
                tar.add(p, arcname=str(arcname), recursive=True)

        sudo_uid = os.environ.get("SUDO_UID")
        sudo_gid = os.environ.get("SUDO_GID")
        if sudo_uid and sudo_gid:
            uid, gid = int(sudo_uid), int(sudo_gid)
            shutil.chown(backup_dir, user=uid, group=gid)
            shutil.chown(archive_path, user=uid, group=gid)

        log_info(f"Local backup archive created: [cyan]{archive_path}[/cyan]")
        return archive_path
    except Exception as e:
        log_error(f"Failed to create local backup archive: {e}")
        return None


def git_create_backup_branch(
    repo_dir: Path,
    configs_dir: Path,
    entries: list[DotfileTarget],
    current_os: str,
    session: PassphraseSession,
) -> None:
    if not (repo_dir / ".git").exists():
        return

    head_check = subprocess.run(
        ["git", "rev-parse", "--quiet", "--verify", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
    )
    if head_check.returncode != 0:
        console.print("[bold yellow]Git repository has no initial commit yet.[/bold yellow]")
        if typer.confirm("Would you like noqte to create an initial baseline commit now?", default=False):
            try:
                subprocess.run(["git", "add", "configs/"], cwd=repo_dir, check=True)
                subprocess.run(["git", "commit", "-m", "Initial dotfiles baseline"], cwd=repo_dir, check=True)
                log_info("Created initial baseline commit.")
            except subprocess.SubprocessError as e:
                log_error(f"Failed to create initial commit: {e}")
                return
        else:
            log_info("Skipping Git snapshot branch for this run.")
            return

    remote_check = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if remote_check.returncode != 0:
        console.print("[bold yellow]No Git remote 'origin' configured for this repository.[/bold yellow]")
        if typer.confirm("Would you like to configure a remote repository now?", default=False):
            url = console.input("[bold cyan]Enter Git remote URL: [/bold cyan]").strip()
            if url:
                try:
                    subprocess.run(["git", "remote", "add", "origin", url], cwd=repo_dir, check=True)
                    log_info(f"Configured remote 'origin' -> {url}")
                except subprocess.SubprocessError as e:
                    log_error(f"Failed to add remote origin: {e}")
                    return
            else:
                log_info("No URL provided. Skipping Git snapshot branch for this run.")
                return
        else:
            log_info("Skipping Git snapshot branch for this run.")
            return

    timestamp = datetime.now().strftime("%d-%m-%Y_%H%M%S")
    backup_branch = f"backup-{timestamp}"
    original_ref: str | None = None
    stashed = False
    committed = False

    try:
        ref_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        original_ref = ref_res.stdout.strip()

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        if status_res.stdout.strip():
            stash_res = subprocess.run(
                ["git", "stash", "push", "-u", "-m", f"noqte_temp_stash_{timestamp}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            stashed = stash_res.returncode == 0 and "No local changes to save" not in stash_res.stdout

        subprocess.run(
            ["git", "checkout", "-b", backup_branch],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        for entry in entries:
            if not entry.is_applicable(current_os):
                continue
            collect_target(entry, configs_dir, session, dry_run=False)

        subprocess.run(["git", "add", "configs/"], cwd=repo_dir, capture_output=True, text=True, check=True)

        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
        if diff_res.returncode == 0:
            log_info("Git snapshot: Host and repository are identical (no diff). Skipping backup branch.")
            return

        diff_status = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        changes = [
            f"  {line.split(maxsplit=1)[0]}\t{line.split(maxsplit=1)[1].removeprefix('configs/')}"
            for line in diff_status.stdout.strip().splitlines()
            if line.strip() and len(line.split(maxsplit=1)) == 2
        ]

        commit_msg = f"Host backup snapshot {timestamp}\n\nChanged files:\n" + "\n".join(changes)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir, capture_output=True, check=True)
        committed = True

        push_res = subprocess.run(
            ["git", "push", "origin", backup_branch],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if push_res.returncode == 0:
            log_info(f"Pushed Git backup snapshot branch: [green]{backup_branch}[/green]")
        else:
            log_warn(f"Created local backup branch '{backup_branch}', push failed: {push_res.stderr.strip()}")

    except Exception as e:
        log_error(f"Git snapshot backup exception: {e}")
    finally:
        if original_ref:
            subprocess.run(["git", "checkout", original_ref], cwd=repo_dir, capture_output=True, check=False)
            if not committed:
                subprocess.run(["git", "branch", "-D", backup_branch], cwd=repo_dir, capture_output=True, check=False)
        if stashed:
            subprocess.run(["git", "stash", "pop"], cwd=repo_dir, capture_output=True, check=False)
