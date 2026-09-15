from __future__ import annotations

from rich.table import Table

from noqte.config import NoqteConfig, PackageTarget
from noqte.logger import console, log_step
from noqte.managers.base import PackageManager
from noqte.managers.brew import BrewManager
from noqte.managers.flatpak import FlatpakManager
from noqte.managers.ir import IRManager
from noqte.managers.pacman import PacmanManager

REGISTRY: dict[str, type[PackageManager]] = {
    "pacman": PacmanManager,
    "brew": BrewManager,
    "flatpak": FlatpakManager,
    "ir": IRManager,
}


def get_manager(name: str) -> PackageManager | None:
    cls = REGISTRY.get(name)
    return cls() if cls else None


def execute_package_pipeline(
    config: NoqteConfig,
    current_os: str,
    preflight: bool = True,
    dry_run: bool = False,
) -> None:
    log_step(f"Auditing packages for platform: [bold]{current_os}[/bold]")

    manager_groups: dict[str, list[PackageTarget]] = {}
    for pkg in config.packages:
        if not pkg.is_applicable(current_os):
            continue

        mgr_name = pkg.manager
        if mgr_name == "pacman" and current_os == "darwin":
            mgr_name = "brew"

        manager_groups.setdefault(mgr_name, []).append(pkg)

    if dry_run:
        table = Table(title="Package Installation Audit (Dry-Run)", show_header=True)
        table.add_column("Manager", style="cyan")
        table.add_column("Package Target", style="magenta")
        table.add_column("Status", style="bold")

        for mgr_name, targets in manager_groups.items():
            mgr = get_manager(mgr_name)
            if not mgr or not mgr.is_available():
                for t in targets:
                    table.add_row(mgr_name, t.name, "[yellow]Manager Missing[/yellow]")
                continue

            missing_names = {t.name for t in mgr.filter_missing(targets)}
            for t in targets:
                if t.name in missing_names:
                    table.add_row(mgr_name, t.name, "[red]Missing (Will Install)[/red]")
                else:
                    table.add_row(mgr_name, t.name, "[green]Satisfied[/green]")

        console.print(table)
        console.print()

    if preflight:
        for mgr_name in manager_groups:
            mgr = get_manager(mgr_name)
            if mgr and mgr.is_available():
                mgr.preflight(dry_run=dry_run)

    for mgr_name, targets in manager_groups.items():
        mgr = get_manager(mgr_name)
        if mgr and mgr.is_available():
            mgr.install(targets, dry_run=dry_run)

    log_step("Package pipeline processing completed.")
