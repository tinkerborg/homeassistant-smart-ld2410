"""Tests for the Smart LD2410 button platform."""

from __future__ import annotations

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.algo.types import GATE_COUNT
from custom_components.smart_ld2410.const import DOMAIN, PERMISSIVE_SENSITIVITY

from .conftest import TEST_ADDRESS, FakeLD2410Client


async def _setup_entry(hass: HomeAssistant) -> tuple[MockConfigEntry, FakeLD2410Client]:
    """Add and set up a config entry, returning it and its fake BLE client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    client = entry.runtime_data.client
    assert isinstance(client, FakeLD2410Client)
    return entry, client


def _entity_id(hass: HomeAssistant) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(
        "button", DOMAIN, f"{TEST_ADDRESS}_set_permissive_thresholds"
    )


async def test_press_writes_permissive_thresholds_to_every_gate(
    hass: HomeAssistant,
) -> None:
    """Pressing the button writes the permissive constant to all 9 gates."""
    _entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass)
    assert entity_id is not None

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(client.set_gate_sensitivity_calls) == GATE_COUNT
    assert client.set_gate_sensitivity_calls == [
        (gate, PERMISSIVE_SENSITIVITY, PERMISSIVE_SENSITIVITY)
        for gate in range(GATE_COUNT)
    ]


async def test_press_failure_raises_home_assistant_error(hass: HomeAssistant) -> None:
    """A BLE command failure surfaces as a HomeAssistantError, not a raw exception."""
    _entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass)
    assert entity_id is not None

    client.command_error = BleakError("write failed")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()
