from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from noqte.config import PackageTarget
from noqte.logger import log_info, log_step, log_warn
from noqte.managers.base import PackageManager


class FlatpakManager(PackageManager):
    name = "flatpak"
    supported_platforms = ("linux",)

    def is_available(self) -> bool:
        return shutil.which("flatpak") is not None

    def preflight(self, dry_run: bool = False) -> None:
        if not self.is_available():
            return
        if dry_run:
            log_info("[DRY-RUN] preflight: flatpak upgrade -y && flatpak uninstall --unused -y")
            return
        log_step("Running Flatpak pre-flight upgrade...")
        subprocess.run(["flatpak", "upgrade", "-y"], check=False)
        subprocess.run(["flatpak", "uninstall", "--unused", "-y"], check=False)

    def get_installed(self) -> set[str]:
        if not self.is_available():
            return set()
        res = subprocess.run(
            ["flatpak", "list", "--columns=application"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {line.strip() for line in res.stdout.splitlines() if line.strip()}

    def install(self, targets: Sequence[PackageTarget], dry_run: bool = False) -> None:
        if not self.is_available():
            log_warn("flatpak not installed on system. Skipping targets.")
            return

        missing = self.filter_missing(targets)
        if not missing:
            log_info(f"Flatpak: All {len(targets)} application(s) satisfied. Skipping.")
            return

        missing_names = [t.name for t in missing]
        if dry_run:
            log_info(f"[DRY-RUN] install: flatpak install -y --noninteractive flathub {' '.join(missing_names)}")
            return

        log_step(f"Installing {len(missing)} missing Flatpak(s)...")
        subprocess.run(
            [
                "flatpak",
                "remote-add",
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ],
            check=False,
        )
        subprocess.run(["flatpak", "install", "-y", "--noninteractive", "flathub", *missing_names], check=False)
