"""Binary sensor platform for Smart LD2410."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartLD2410ConfigEntry
from .const import DOMAIN
from .coordinator import SmartLD2410Coordinator, detector_mode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartLD2410ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform for Smart LD2410."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            OccupancyBinarySensor(coordinator),
            AdaptationFrozenBinarySensor(coordinator),
        ]
    )


class _SmartLD2410BinarySensorEntity(
    CoordinatorEntity[SmartLD2410Coordinator], BinarySensorEntity
):
    """Common wiring for Smart LD2410 binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartLD2410Coordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})

    @property
    def available(self) -> bool:
        """Unavailable while the BLE client reports the device disconnected."""
        return self.coordinator.available and super().available


class OccupancyBinarySensor(_SmartLD2410BinarySensorEntity):
    """Whether the detector currently reads the room as occupied."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "occupancy")

    @property
    def is_on(self) -> bool:
        """Return DetectorOutput.occupied.

        During baseline cold start the detector already passes through
        device_occupancy via this same field, so no special-casing is needed
        here.
        """
        return self.coordinator.data.occupied

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The occupancy attributes the interfaces contract (§1.1) defines."""
        data = self.coordinator.data
        active_gates = data.active_gates
        return {
            "confidence": data.confidence,
            "active_gate_min": min(active_gates) if active_gates else None,
            "active_gate_max": max(active_gates) if active_gates else None,
            "mode": detector_mode(data),
            "boundary_gate": data.boundary_gate,
            "leading_gate": data.leading_gate,
            "ownership": data.ownership,
            "retention_max": data.retention_max,
        }


class AdaptationFrozenBinarySensor(_SmartLD2410BinarySensorEntity):
    """Whether baseline adaptation is currently suppressed."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "adaptation_frozen"

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "adaptation_frozen")

    @property
    def is_on(self) -> bool:
        """Return the detector's adaptation_frozen flag."""
        return self.coordinator.data.adaptation_frozen
