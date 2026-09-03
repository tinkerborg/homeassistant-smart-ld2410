"""Config flow for the Smart LD2410 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_BASELINE_WINDOW_HOURS,
    CONF_ENTER_SCORE,
    CONF_EXIT_SCORE,
    CONF_FREEZE_HOLD_SECONDS,
    CONF_HOLD_SECONDS,
    CONF_K,
    CONF_SUPPORT_TAU_S,
    DEFAULT_BASELINE_WINDOW_HOURS,
    DEFAULT_ENTER_SCORE,
    DEFAULT_EXIT_SCORE,
    DEFAULT_FREEZE_HOLD_SECONDS,
    DEFAULT_HOLD_SECONDS,
    DEFAULT_K,
    DEFAULT_PASSWORD,
    DEFAULT_SUPPORT_TAU_S,
    DOMAIN,
    LD2410_SERVICE_UUID,
    PASSWORD_LENGTH,
)

PASSWORD_SCHEMA = {
    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): TextSelector(
        TextSelectorConfig()
    ),
}


def _validate_password(user_input: dict[str, Any], errors: dict[str, str]) -> None:
    """Populate errors with invalid_password_length if the password is malformed.

    LD2410 BLE passwords are always exactly 6 ASCII characters; this only
    checks the shape of the value, it does not verify it against the device.
    """
    password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
    if len(password) != PASSWORD_LENGTH or not password.isascii():
        errors["base"] = "invalid_password_length"


class SmartLD2410ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart LD2410."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered via bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a bluetooth-discovered device."""
        assert self._discovery_info is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            _validate_password(user_input, errors)
            if not errors:
                return self.async_create_entry(
                    title=self._discovery_info.name,
                    data={
                        CONF_ADDRESS: self._discovery_info.address,
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD),
                    },
                )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(PASSWORD_SCHEMA),
            description_placeholders={"name": self._discovery_info.name},
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow started by the user picking a discovered device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            _validate_password(user_input, errors)
            if not errors:
                address = user_input[CONF_ADDRESS]
                discovery_info = self._discovered_devices[address]
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=discovery_info.name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD),
                    },
                )

        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if LD2410_SERVICE_UUID not in discovery_info.service_uuids:
                continue
            self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{info.name} ({address})"
                            for address, info in self._discovered_devices.items()
                        }
                    ),
                    **PASSWORD_SCHEMA,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the configured bluetooth password."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None:
            _validate_password(user_input, errors)
            if not errors:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(PASSWORD_SCHEMA), reconfigure_entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SmartLD2410OptionsFlow:
        """Create the options flow."""
        return SmartLD2410OptionsFlow()


class SmartLD2410OptionsFlow(OptionsFlow):
    """Handle tuning knob changes for an existing Smart LD2410 entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_K, default=options.get(CONF_K, DEFAULT_K)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.5, max=20, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_BASELINE_WINDOW_HOURS,
                    default=options.get(
                        CONF_BASELINE_WINDOW_HOURS, DEFAULT_BASELINE_WINDOW_HOURS
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=48, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_ENTER_SCORE,
                    default=options.get(CONF_ENTER_SCORE, DEFAULT_ENTER_SCORE),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.5, max=20, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_EXIT_SCORE,
                    default=options.get(CONF_EXIT_SCORE, DEFAULT_EXIT_SCORE),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.1, max=20, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_HOLD_SECONDS,
                    default=options.get(CONF_HOLD_SECONDS, DEFAULT_HOLD_SECONDS),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=600, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_FREEZE_HOLD_SECONDS,
                    default=options.get(
                        CONF_FREEZE_HOLD_SECONDS, DEFAULT_FREEZE_HOLD_SECONDS
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=3600, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_SUPPORT_TAU_S,
                    default=options.get(CONF_SUPPORT_TAU_S, DEFAULT_SUPPORT_TAU_S),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.1, max=30, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
