"""Select platform for Smart LD2410."""

from __future__ import annotations

import time

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartLD2410ConfigEntry
from .const import DOMAIN, LABEL_NONE, LABEL_OPTIONS
from .coordinator import SmartLD2410Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartLD2410ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select platform for Smart LD2410."""
    async_add_entities([LabelSelect(entry.runtime_data.coordinator)])


class LabelSelect(CoordinatorEntity[SmartLD2410Coordinator], SelectEntity):
    """Ground-truth activity label, recorded as an event on every change."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "label"
    _attr_options = list(LABEL_OPTIONS)

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_label"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})
        self._attr_current_option = LABEL_NONE

    @property
    def available(self) -> bool:
        """Unavailable while the BLE client reports the device disconnected."""
        return self.coordinator.available and super().available

    async def async_select_option(self, option: str) -> None:
        """Record the new label and enqueue a label event at the current time."""
        self._attr_current_option = option
        self.async_write_ha_state()
        self.coordinator.enqueue_label_event(time.time(), option)
