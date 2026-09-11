"""Tests for the Smart LD2410 options flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.const import CONF_K, DEFAULT_K, DOMAIN

from .conftest import TEST_ADDRESS


async def test_options_flow_updates_config(hass: HomeAssistant) -> None:
    """The options flow shows current defaults and persists a changed value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({})[CONF_K] == DEFAULT_K

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "k": DEFAULT_K + 1.0,
            "baseline_window_hours": 12,
            "enter_score": 3.0,
            "exit_score": 1.5,
            "hold_seconds": 30,
            "freeze_hold_seconds": 60,
            "support_tau_s": 1.0,
            "diagnostic": {
                "t_dwell_s": 60,
                "t_brief_s": 10,
                "n_bleed_min": 20,
                "stats_half_life_days": 30,
                "raw_retention_days": 7,
                "summary_retention_days": 365,
            },
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["k"] == DEFAULT_K + 1.0
    assert entry.options["t_dwell_s"] == 60


async def test_reconfigure_rejects_wrong_length_password_then_accepts(
    hass: HomeAssistant,
) -> None:
    """The reconfigure step rejects a malformed password and stores a valid one."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "short"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_password_length"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "secret"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "secret"
