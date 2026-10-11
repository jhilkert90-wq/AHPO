"""Tests for the hot-water (HW) control strategy and its coordinator integration."""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def _module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    _module("homeassistant")
    core = _module("homeassistant.core")
    helpers = _module("homeassistant.helpers")
    event = _module("homeassistant.helpers.event")
    for attr in ("Event", "EventStateChangedData", "HomeAssistant"):
        if not hasattr(core, attr):
            setattr(core, attr, object)
    if not hasattr(core, "callback"):
        core.callback = lambda f: f
    for attr in ("async_track_state_change_event", "async_track_time_interval"):
        if not hasattr(event, attr):
            setattr(event, attr, lambda *a, **k: (lambda: None))
    helpers.event = event

    root = Path(__file__).resolve().parents[2] / "custom_components"
    pkg = types.ModuleType("custom_components")
    pkg.__path__ = [str(root)]
    sys.modules.setdefault("custom_components", pkg)
    integ = types.ModuleType("custom_components.adaptive_hydraulic_optimizer")
    integ.__path__ = [str(root / "adaptive_hydraulic_optimizer")]
    sys.modules.setdefault("custom_components.adaptive_hydraulic_optimizer", integ)


_install_stubs()
_P = "custom_components.adaptive_hydraulic_optimizer"
hw = importlib.import_module(f"{_P}.core.hw_strategy")
coord_mod = importlib.import_module(f"{_P}.coordinator")


def test_controller_directions_and_limits() -> None:
    c = hw.DhwController(offset_k=1.0, kp=5.0, deadband_k=0.2, max_step_percent=5.0, min_speed=15.0)
    assert c.update(51.0, 50.0, 50.0) == 50.0            # exactly +1 K -> deadband
    assert c.update(55.0, 50.0, 50.0) == 55.0            # too hot -> faster, step-limited
    assert c.update(45.0, 50.0, 50.0) == 45.0            # too cold -> slower
    assert c.update(40.0, 50.0, 17.0) == 15.0            # floor
    assert c.update(60.0, 50.0, 98.0) == 100.0           # ceiling


def test_derivative_damps_approach() -> None:
    c = hw.DhwController(offset_k=1.0, kp=1.0, deadband_k=0.2, max_step_percent=5.0, kd=4.0)
    c.update(56.0, 50.0, 50.0)                           # error +5, no trend yet
    assert c.update(52.5, 50.0, 50.0) == 45.0            # still hot but falling fast -> slows (step-limited)


def test_mode_resolution() -> None:
    r = coord_mod._resolve_operating_mode
    assert r("hw") == "dhw" and r("Warmwasser") == "dhw" and r("hotwater") == "dhw"
    assert r("custom", "custom") == "dhw"
    assert r("heat") == "heat" and r("cool") == "cool" and r("off") is None


class _State:
    def __init__(self, state: str) -> None:
        self.state = state


class _States:
    def __init__(self) -> None:
        self.d: dict[str, _State] = {}

    def get(self, eid):
        return self.d.get(eid)


class _Hass:
    def __init__(self) -> None:
        self.states = _States()
        self.writes: list[float] = []

    def async_create_task(self, coro):
        coro.close()


def _make(hass):
    emap = {
        "primary_flow_temp": "s.flow", "dhw_target_temp": "s.target",
        "compressor_frequency": "s.freq", "charge_pump_speed_input": "s.speed",
        "operating_mode": "s.mode", "error_status": "s.error",
    }
    c = coord_mod.AhpoCoordinator(hass, emap, None, None, dhw_standby_speed=30.0, dhw_control_interval_s=5.0)
    c.written = []
    c._write_dhw_speed = lambda s: (c.written.append(s), c._remember_last_written_speed(s, hw.DHW_MODE))
    return c


def _set(hass, **kw):
    names = {
        "flow": "s.flow", "target": "s.target", "freq": "s.freq",
        "speed": "s.speed", "mode": "s.mode", "error": "s.error",
    }
    for k, v in kw.items():
        hass.states.d[names[k]] = _State(str(v))


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_standby_written_once_and_regulation_resumes() -> None:
    h = _Hass()
    c = _make(h)
    _set(h, flow=45, target=50, freq=0, speed=40, mode="hw")
    c._tick(T0)
    c._tick(T0 + timedelta(seconds=6))
    assert c.written == [30.0]                       # standby only on entry
    _set(h, freq=50, flow=55)
    c._tick(T0 + timedelta(seconds=12))
    assert c.written == [30.0, 35.0]                 # too hot -> faster, from standby


def test_hw_interval_and_missing_inputs() -> None:
    h = _Hass()
    c = _make(h)
    _set(h, flow=55, target=50, freq=50, speed=40, mode="hw")
    c._tick(T0)
    c._tick(T0 + timedelta(seconds=2))               # within interval -> skipped
    assert c.written == [45.0]
    c.dhw_control_interval_s = 1.0
    c._tick(T0 + timedelta(seconds=3))
    assert c.written == [45.0, 50.0]
    h.states.d["s.target"] = _State("unavailable")
    c._tick(T0 + timedelta(seconds=10))
    assert c.written == [45.0, 50.0]


def test_error_status_and_pump_write_failure_suppress_dhw_writes() -> None:
    for fault in ("error_status", "pump_write_error"):
        h = _Hass()
        c = _make(h)
        _set(h, flow=55, target=50, freq=50, speed=40, mode="hw", error="off")
        c._tick(T0)
        assert c.written == [45.0]
        assert c._dhw_controller.last_error_k is not None

        _set(h, freq=0)
        if fault == "error_status":
            _set(h, error="on")
        else:
            c.pump_write_error = True
        c._tick(T0 + timedelta(seconds=6))
        assert c.written == [45.0]
        assert c._dhw_controller.last_error_k is None

        if fault == "error_status":
            _set(h, error="off")
        else:
            c.pump_write_error = False
        _set(h, freq=50)
        c._tick(T0 + timedelta(seconds=12))
        assert c.written == [45.0, 50.0]


def test_leaving_hw_resets_state() -> None:
    h = _Hass()
    c = _make(h)
    _set(h, flow=55, target=50, freq=50, speed=40, mode="hw")
    c._tick(T0)
    assert c.dhw_active
    _set(h, mode="heat")
    c._tick(T0 + timedelta(seconds=10))
    assert not c.dhw_active and c._last_written_speed is None
    assert c._dhw_controller.last_error_k is None


class _Services:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.error: Exception | None = None

    async def async_call(self, domain, service, data, blocking=True):
        self.calls.append((domain, service, data))
        if self.error is not None:
            raise self.error


@pytest.mark.parametrize(
    ("mode", "output_key"),
    [
        ("heat", "charge_pump_speed_output_heat"),
        ("cool", "charge_pump_speed_output_cool"),
        ("dhw", "charge_pump_speed_output_dhw"),
    ],
)
def test_mode_specific_output_overrides(mode: str, output_key: str) -> None:
    h = _Hass()
    h.services = _Services()
    c = coord_mod.AhpoCoordinator(
        h,
        {
            "charge_pump_speed_output": "number.general",
            "charge_pump_speed_output_heat": "number.heat",
            "charge_pump_speed_output_cool": "number.cool",
            "charge_pump_speed_output_dhw": "number.dhw",
        },
        None,
        None,
    )

    asyncio.run(c._async_write_pump_speed(40.0, mode))

    expected_entity = {
        "charge_pump_speed_output_heat": "number.heat",
        "charge_pump_speed_output_cool": "number.cool",
        "charge_pump_speed_output_dhw": "number.dhw",
    }[output_key]
    assert h.services.calls[0][2] == {"entity_id": expected_entity, "value": 40.0}
    assert not c.pump_write_error


@pytest.mark.parametrize("mode", ["heat", "cool", "dhw"])
def test_modes_fall_back_to_general_output(mode: str) -> None:
    h = _Hass()
    h.services = _Services()
    c = coord_mod.AhpoCoordinator(
        h, {"charge_pump_speed_output": "input_number.general"}, None, None
    )

    asyncio.run(c._async_write_pump_speed(40.0, mode))

    assert h.services.calls[0][2] == {"entity_id": "input_number.general", "value": 40.0}


def test_missing_output_is_passive_without_write_error() -> None:
    h = _Hass()
    h.services = _Services()
    c = coord_mod.AhpoCoordinator(h, {}, None, None)

    asyncio.run(c._async_write_pump_speed(40.0, "heat"))

    assert h.services.calls == []
    assert not c.pump_write_error


def test_output_clamping_and_write_errors() -> None:
    h = _Hass()
    h.services = _Services()
    c = coord_mod.AhpoCoordinator(
        h,
        {"charge_pump_speed_output": "number.pump"},
        None,
        None,
        min_charge_pump_speed=15.0,
    )
    c.pump_write_error = True

    asyncio.run(c._async_write_pump_speed(10.0, "heat"))

    assert h.services.calls[0][2] == {"entity_id": "number.pump", "value": 15.0}
    assert not c.pump_write_error

    c._entity_map["charge_pump_speed_output"] = "sensor.unsupported"
    asyncio.run(c._async_write_pump_speed(40.0, "heat"))
    assert c.pump_write_error

    c._entity_map["charge_pump_speed_output"] = "number.pump"
    h.services.error = RuntimeError("service failure")
    asyncio.run(c._async_write_pump_speed(40.0, "heat"))
    assert c.pump_write_error


def test_target_switch_uses_last_speed_for_selected_output(monkeypatch) -> None:
    h = _Hass()
    entity_map = {key: f"s.{key}" for key in coord_mod.REQUIRED_ENTITY_KEYS}
    entity_map.update(
        {
            "operating_mode": "s.mode",
            "charge_pump_speed_output_heat": "number.heat",
            "charge_pump_speed_output_cool": "number.cool",
        }
    )
    c = coord_mod.AhpoCoordinator(
        h, entity_map, None, None, min_speed_step_percent=1.0
    )
    c._detector.observe = lambda **kwargs: coord_mod.Observation(
        timestamp=kwargs["timestamp"],
        outdoor_temp=5.0,
        compressor_frequency=50.0,
        charge_pump_speed=40.0,
        cop=3.0,
        spread_error=0.0,
    )
    c._learning_engine = SimpleNamespace(
        process=lambda *args, **kwargs: SimpleNamespace(
            phase=coord_mod.Phase.ACTIVE,
            proposed_charge_pump_speed=50.0,
            cell=None,
        )
    )
    monkeypatch.setattr(coord_mod, "calculate_cop_for_row", lambda *args, **kwargs: 3.0)
    monkeypatch.setattr(
        coord_mod, "calculate_spread_error_for_row", lambda *args, **kwargs: 0.0
    )
    for key in coord_mod.REQUIRED_ENTITY_KEYS:
        h.states.d[f"s.{key}"] = _State("40")

    _set(h, mode="heat")
    c._tick(T0)
    _set(h, mode="cool")
    c._tick(T0 + timedelta(seconds=5))

    assert c._last_written_speeds[("entity", "number.heat")] == 50.0
    assert c._last_written_speeds[("entity", "number.cool")] == 50.0


def test_dhw_transition_starts_from_dhw_target_speed() -> None:
    h = _Hass()
    c = _make(h)
    c._entity_map["charge_pump_speed_output_dhw"] = "number.dhw"
    c._last_written_speed = 50.0
    c._last_written_speeds[("entity", "number.heat")] = 50.0
    _set(h, flow=55, target=50, freq=50, speed=40, mode="hw")

    c._tick(T0)

    assert c.written == [45.0]
    assert c._last_written_speeds[("entity", "number.dhw")] == 45.0
