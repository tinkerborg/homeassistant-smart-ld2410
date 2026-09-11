"""Button platform for Smart LD2410."""

from __future__ import annotations

import logging
from typing import Any

from bleak.exc import BleakError

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartLD2410ConfigEntry
from .algo.detector import Detector
from .algo.types import GATE_COUNT
from .ble.client import LD2410Client
from .const import DOMAIN, PERMISSIVE_SENSITIVITY
from .coordinator import SmartLD2410Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartLD2410ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform for Smart LD2410."""
    runtime_data = entry.runtime_data
    async_add_entities(
        [
            SetPermissiveThresholdsButton(
                runtime_data.coordinator, runtime_data.client
            ),
            ResetLearningButton(
                runtime_data.coordinator, runtime_data.baseline_store
            ),
        ]
    )


class SetPermissiveThresholdsButton(
    CoordinatorEntity[SmartLD2410Coordinator], ButtonEntity
):
    """Writes permissive gate sensitivities to the device.

    The detector makes the real enter/exit decision from residuals computed
    host-side; the device's own occupancy bit only serves as a comparison
    baseline during cold start. Pressing this button sets every gate's
    moving/static sensitivity as low as possible so that baseline never
    filters out signal the detector should see.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "set_permissive_thresholds"

    def __init__(
        self, coordinator: SmartLD2410Coordinator, client: LD2410Client
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{coordinator.address}_set_permissive_thresholds"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})

    @property
    def available(self) -> bool:
        """Unavailable while the BLE client reports the device disconnected."""
        return self.coordinator.available and super().available

    async def async_press(self) -> None:
        """Write permissive sensitivities to every gate, then log the readback."""
        try:
            for gate in range(GATE_COUNT):
                await self._client.set_gate_sensitivity(
                    gate, PERMISSIVE_SENSITIVITY, PERMISSIVE_SENSITIVITY
                )
            params = await self._client.read_params()
        except (BleakError, ConnectionError, TimeoutError) as err:
            raise HomeAssistantError(
                "Failed to set permissive gate thresholds on the LD2410 device"
            ) from err

        _LOGGER.info(
            "%s: Set permissive thresholds; device reports move=%s static=%s",
            self.coordinator.address,
            params.move_sensitivities,
            params.still_sensitivities,
        )


class ResetLearningButton(CoordinatorEntity[SmartLD2410Coordinator], ButtonEntity):
    """Wipes a sensor's persisted learning and swaps in a fresh detector."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_learning"

    def __init__(
        self,
        coordinator: SmartLD2410Coordinator,
        baseline_store: Store[dict[str, Any]],
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._baseline_store = baseline_store
        self._attr_unique_id = f"{coordinator.address}_reset_learning"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})

    async def async_press(self) -> None:
        """Discard persisted learning, then swap in a fresh detector."""
        await self._baseline_store.async_remove()
        self.coordinator.detector = Detector(self.coordinator.detector.config)

        _LOGGER.info(
            "%s: Reset learning; occupancy is in passthrough until the new "
            "baseline warms up",
            self.coordinator.address,
        )
