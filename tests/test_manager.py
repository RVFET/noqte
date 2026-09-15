from __future__ import annotations

from noqte.config import PackageTarget
from noqte.managers import get_manager
from noqte.managers.pacman import PacmanManager


def test_registry_lookups():
    assert isinstance(get_manager("pacman"), PacmanManager)
    assert get_manager("unknown_mgr") is None


def test_pacman_prefix_filtering(monkeypatch):
    mgr = PacmanManager()
    monkeypatch.setattr(mgr, "get_installed", lambda: {"dms-shell", "ripgrep"})

    targets = [
        PackageTarget(name="extra/dms-shell"),
        PackageTarget(name="ripgrep"),
        PackageTarget(name="eza"),
    ]

    missing = mgr.filter_missing(targets)
    assert len(missing) == 1
    assert missing[0].name == "eza"
