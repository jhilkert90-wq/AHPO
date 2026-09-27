"""Regression tests for AHPO button entities used by the Home Assistant integration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
import types


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    button_mod = types.ModuleType("homeassistant.components.button")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")

    class ButtonEntity:
        async def async_added_to_hass(self) -> None:
            return None

    class ConfigEntry:
        def __init__(self, entry_id: str) -> None:
            self.entry_id = entry_id

    class HomeAssistant:
        pass

    class DeviceInfo(dict):
        pass

    button_mod.ButtonEntity = ButtonEntity
    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    entity_platform.AddEntitiesCallback = object
    device_registry.DeviceInfo = DeviceInfo

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.button"] = button_mod
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.device_registry"] = device_registry


_install_homeassistant_stubs()


def _install_custom_component_package_stubs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    custom_components_root = repo_root / "custom_components"
    integration_root = custom_components_root / "adaptive_hydraulic_optimizer"

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(custom_components_root)]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    integration_pkg = types.ModuleType("custom_components.adaptive_hydraulic_optimizer")
    integration_pkg.__path__ = [str(integration_root)]
    sys.modules["custom_components.adaptive_hydraulic_optimizer"] = integration_pkg


_install_custom_component_package_stubs()

_button_module = importlib.import_module("custom_components.adaptive_hydraulic_optimizer.button")
AhpoResetMapButton = _button_module.AhpoResetMapButton
AhpoResetConfidenceButton = _button_module.AhpoResetConfidenceButton


@dataclass
class _FakeCell:
    confidence_score: float


class _FakeMap:
    def __init__(self, cells: list[_FakeCell] | None = None) -> None:
        self._cells = cells or []
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True

    def all_cells(self) -> list[_FakeCell]:
        return self._cells


class _FakeEntry:
    def __init__(self, entry_id: str = "entry-1") -> None:
        self.entry_id = entry_id


def test_reset_map_button_press_clears_both_maps() -> None:
    cool_map = _FakeMap()
    heat_map = _FakeMap()
    button = AhpoResetMapButton(cool_map, heat_map, _FakeEntry())

    asyncio.run(button.async_press())

    assert cool_map.cleared is True
    assert heat_map.cleared is True


def test_reset_confidence_button_press_resets_all_cells() -> None:
    cool_cells = [_FakeCell(0.2), _FakeCell(0.7)]
    heat_cells = [_FakeCell(0.4)]
    button = AhpoResetConfidenceButton(_FakeMap(cool_cells), _FakeMap(heat_cells), _FakeEntry())

    asyncio.run(button.async_press())

    assert [cell.confidence_score for cell in cool_cells + heat_cells] == [0.0, 0.0, 0.0]


def test_buttons_clear_last_pressed_on_add_to_hass() -> None:
    cool_map = _FakeMap()
    heat_map = _FakeMap()
    map_button = AhpoResetMapButton(cool_map, heat_map, _FakeEntry())
    confidence_button = AhpoResetConfidenceButton(cool_map, heat_map, _FakeEntry())

    restored_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    map_button._attr_last_pressed = restored_ts
    confidence_button._attr_last_pressed = restored_ts

    asyncio.run(map_button.async_added_to_hass())
    asyncio.run(confidence_button.async_added_to_hass())

    assert map_button._attr_last_pressed is None
    assert confidence_button._attr_last_pressed is None
