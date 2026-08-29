"""Tests for Smart LD2410 setup and unload."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.const import DOMAIN


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """A config entry sets up and unloads cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
