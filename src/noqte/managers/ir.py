from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from noqte.config import PackageTarget
from noqte.logger import log_info, log_step, log_warn
from noqte.managers.base import PackageManager


class IRManager(PackageManager):
    name = "ir"
    supported_platforms = ("linux", "darwin")

    def is_available(self) -> bool:
        return shutil.which("ir") is not None

    def preflight(self, dry_run: bool = False) -> None:
        if not self.is_available():
            return
        if dry_run:
            log_info("[DRY-RUN] preflight: ir upgrade")
            return
        log_step("Running ir (install-release) pre-flight upgrade...")
        subprocess.run(["ir", "upgrade"], check=False)

    def get_installed(self) -> set[str]:
        if not self.is_available():
            return set()
        res = subprocess.run(["ir", "ls"], capture_output=True, text=True, check=False)
        return set(res.stdout.splitlines()) if res.returncode == 0 else set()

    def filter_missing(self, targets: Sequence[PackageTarget]) -> list[PackageTarget]:
        installed_output = "\n".join(self.get_installed())
        missing: list[PackageTarget] = []
        for t in targets:
            url = t.name
            slug = url.split("/")[-1]
            if url not in installed_output and slug not in installed_output:
                missing.append(t)
        return missing

    def install(self, targets: Sequence[PackageTarget], dry_run: bool = False) -> None:
        if not self.is_available():
            log_warn("ir (install-release) binary not found in PATH. Skipping targets.")
            return

        missing = self.filter_missing(targets)
        if not missing:
            log_info(f"IR: All {len(targets)} release binary/binaries satisfied. Skipping.")
            return

        for t in missing:
            if dry_run:
                log_info(f"[DRY-RUN] install: ir get {t.name}")
            else:
                log_step(f"Fetching release binary via ir: {t.name}")
                subprocess.run(["ir", "get", t.name], check=False)
