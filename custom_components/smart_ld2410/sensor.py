"""Sensor platform for Smart LD2410."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartLD2410ConfigEntry
from .algo.types import GATE_COUNT
from .const import DOMAIN
from .coordinator import SmartLD2410Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartLD2410ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform for Smart LD2410."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        ConfidenceSensor(coordinator),
        ActiveGateRangeSensor(coordinator),
        TargetDistanceSensor(coordinator),
        BaselineAgeSensor(coordinator),
    ]
    entities.extend(
        ResidualSensor(coordinator, "move", gate) for gate in range(GATE_COUNT)
    )
    entities.extend(
        ResidualSensor(coordinator, "still", gate) for gate in range(GATE_COUNT)
    )
    async_add_entities(entities)


class _SmartLD2410SensorEntity(CoordinatorEntity[SmartLD2410Coordinator], SensorEntity):
    """Common wiring for Smart LD2410 sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartLD2410Coordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})

    @property
    def available(self) -> bool:
        """Unavailable while the BLE client reports the device disconnected."""
        return self.coordinator.available and super().available


class ConfidenceSensor(_SmartLD2410SensorEntity):
    """Detector confidence, as a percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "confidence")

    @property
    def native_value(self) -> float:
        """Return DetectorOutput.confidence scaled to 0-100."""
        return self.coordinator.data.confidence * 100


class ActiveGateRangeSensor(_SmartLD2410SensorEntity):
    """The min-max span of the currently active gate run."""

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "active_gate_range")

    @property
    def native_value(self) -> str:
        """Return e.g. "3-5", a single gate number, or "clear"."""
        gates = self.coordinator.data.active_gates
        if not gates:
            return "clear"
        low, high = min(gates), max(gates)
        return f"{low}" if low == high else f"{low}–{high}"


class TargetDistanceSensor(_SmartLD2410SensorEntity):
    """Detected target distance, from the latest raw frame."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "target_distance")

    @property
    def native_value(self) -> int | None:
        """Return the latest frame's target_distance_cm, if any frame yet."""
        frame = self.coordinator.latest_frame
        return frame.target_distance_cm if frame is not None else None


class BaselineAgeSensor(_SmartLD2410SensorEntity):
    """How much data has accumulated into the noise baseline."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartLD2410Coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "baseline_age")

    @property
    def native_value(self) -> float:
        """Return DetectorOutput.baseline_age_s."""
        return self.coordinator.data.baseline_age_s


class ResidualSensor(_SmartLD2410SensorEntity):
    """One per-gate, per-channel residual (z-score against the baseline).

    High-rate tuning entities: disabled by default so the recorder never
    sees them unless a user opts in.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: SmartLD2410Coordinator, channel: str, gate: int
    ) -> None:
        """Initialize the entity for one (channel, gate) pair."""
        self._channel = channel
        self._gate = gate
        super().__init__(coordinator, f"residual_{channel}_{gate}")

    @property
    def native_value(self) -> float:
        """Return the residual for this channel/gate from the latest output."""
        data = self.coordinator.data
        residuals = data.residuals_move if self._channel == "move" else data.residuals_still
        return residuals[self._gate]
