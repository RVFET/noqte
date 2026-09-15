from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from noqte.config import PackageTarget


class PackageManager(ABC):
    name: ClassVar[str]
    supported_platforms: ClassVar[tuple[str, ...]] = ("linux", "darwin")

    @abstractmethod
    def is_available(self) -> bool:
        """Check if package manager binary is present on the host."""
        ...

    @abstractmethod
    def preflight(self, dry_run: bool = False) -> None:
        """Run system upgrade / index refresh for this manager."""
        ...

    @abstractmethod
    def get_installed(self) -> set[str]:
        """Return normalized set of currently installed package names/identifiers."""
        ...

    def filter_missing(self, targets: Sequence[PackageTarget]) -> list[PackageTarget]:
        """Compute delta of targets that are not satisfied."""
        installed = self.get_installed()
        return [t for t in targets if t.name not in installed]

    @abstractmethod
    def install(self, targets: Sequence[PackageTarget], dry_run: bool = False) -> None:
        """Install missing packages."""
        ...
