from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from rich.console import Console

console = Console()


def get_log_file_path() -> Path:
    """Resolve log file path according to XDG State specifications."""
    state_home = os.environ.get("XDG_STATE_HOME")
    base_dir = Path(state_home) if state_home else Path.home() / ".local" / "state"
    log_dir = base_dir / "noqte"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "usage.log"

    # Normalize permissions if running under sudo
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if sudo_uid and sudo_gid:
        try:
            uid, gid = int(sudo_uid), int(sudo_gid)
            shutil.chown(log_dir, user=uid, group=gid)
            if log_file.exists():
                shutil.chown(log_file, user=uid, group=gid)
        except (OSError, LookupError):
            pass

    return log_file


def init_file_logger() -> logging.Logger:
    log = logging.getLogger("noqte")
    log.setLevel(logging.INFO)

    file_path = get_log_file_path()
    handler = logging.FileHandler(file_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log


logger = init_file_logger()


def log_step(msg: str) -> None:
    console.print(f"[bold blue]::[/bold blue] {msg}")
    logger.info(msg)


def log_info(msg: str) -> None:
    console.print(f"   {msg}")
    logger.info(msg)


def log_warn(msg: str) -> None:
    console.print(f"[bold yellow]WARNING:[/bold yellow] {msg}")
    logger.warning(msg)


def log_error(msg: str) -> None:
    console.print(f"[bold red]ERROR:[/bold red] {msg}")
    logger.error(msg)
