from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from noqte.config import PackageTarget
from noqte.logger import log_error, log_info, log_step
from noqte.managers.base import PackageManager


class BrewManager(PackageManager):
    name = "brew"
    supported_platforms = ("darwin",)

    def is_available(self) -> bool:
        return shutil.which("brew") is not None

    def preflight(self, dry_run: bool = False) -> None:
        if dry_run:
            log_info("[DRY-RUN] preflight: brew update && brew upgrade")
            return
        log_step("Running Homebrew pre-flight update & upgrade...")
        subprocess.run(["brew", "update"], check=True)
        subprocess.run(["brew", "upgrade"], check=True)

    def get_installed(self) -> set[str]:
        res_f = subprocess.run(["brew", "list", "--formula"], capture_output=True, text=True, check=False)
        res_c = subprocess.run(["brew", "list", "--cask"], capture_output=True, text=True, check=False)
        formulae = set(res_f.stdout.splitlines()) if res_f.returncode == 0 else set()
        casks = set(res_c.stdout.splitlines()) if res_c.returncode == 0 else set()
        return formulae | casks

    def filter_missing(self, targets: Sequence[PackageTarget]) -> list[PackageTarget]:
        installed = self.get_installed()
        missing: list[PackageTarget] = []
        for t in targets:
            name = t.name
            if isinstance(t.mac, str):
                name = t.mac
            elif t.mac is not None and t.mac.name:
                name = t.mac.name
            if name not in installed:
                missing.append(t)
        return missing

    def install(self, targets: Sequence[PackageTarget], dry_run: bool = False) -> None:
        if not self.is_available():
            log_error("Homebrew not found in PATH.")
            return

        missing = self.filter_missing(targets)
        if not missing:
            log_info(f"Brew: All {len(targets)} package(s) satisfied. Skipping.")
            return

        formulae: list[str] = []
        casks: list[str] = []

        for t in missing:
            name = t.name
            is_cask = False
            if isinstance(t.mac, str):
                name = t.mac
            elif t.mac is not None:
                name = t.mac.name or name
                is_cask = t.mac.cask

            if is_cask:
                casks.append(name)
            else:
                formulae.append(name)

        if formulae:
            if dry_run:
                log_info(f"[DRY-RUN] install: brew install {' '.join(formulae)}")
            else:
                log_step(f"Installing {len(formulae)} missing Homebrew formulae...")
                subprocess.run(["brew", "install", *formulae], check=False)

        if casks:
            if dry_run:
                log_info(f"[DRY-RUN] install: brew install --cask {' '.join(casks)}")
            else:
                log_step(f"Installing {len(casks)} missing Homebrew casks...")
                subprocess.run(["brew", "install", "--cask", *casks], check=False)
