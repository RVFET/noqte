from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from noqte.config import PackageTarget
from noqte.logger import log_info, log_step
from noqte.managers.base import PackageManager


class PacmanManager(PackageManager):
    name = "pacman"
    supported_platforms = ("linux",)

    def is_available(self) -> bool:
        return shutil.which("pacman") is not None

    def preflight(self, dry_run: bool = False) -> None:
        cmd = ["paru", "-Syyu"] if shutil.which("paru") else ["sudo", "pacman", "-Syyu"]
        if dry_run:
            log_info(f"[DRY-RUN] preflight: {' '.join(cmd)}")
            return
        log_step(f"Running pacman pre-flight upgrade ({' '.join(cmd)})...")
        subprocess.run(cmd, check=True)

    def get_installed(self) -> set[str]:
        res = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True, check=False)
        return set(res.stdout.splitlines()) if res.returncode == 0 else set()

    def filter_missing(self, targets: Sequence[PackageTarget]) -> list[PackageTarget]:
        installed = self.get_installed()
        # Handling repository prefixes like extra/dms-shell
        return [t for t in targets if t.name.split("/")[-1] not in installed]

    def install(self, targets: Sequence[PackageTarget], dry_run: bool = False) -> None:
        missing = self.filter_missing(targets)
        if not missing:
            log_info(f"Pacman: All {len(targets)} package(s) satisfied. Skipping.")
            return

        installer = ["paru"] if shutil.which("paru") else ["sudo", "pacman"]
        cmd = [*installer, "-S", *[t.name for t in missing]]

        if dry_run:
            log_info(f"[DRY-RUN] install: {' '.join(cmd)}")
            return

        log_step(f"Installing {len(missing)} missing pacman package(s)...")
        subprocess.run(cmd, check=False)
