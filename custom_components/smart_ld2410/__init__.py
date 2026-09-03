"""The Smart LD2410 integration."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .algo.baseline import BaselineModel
from .algo.detector import Detector
from .algo.types import DetectorConfig
from .ble.client import LD2410Client
from .const import (
    BASELINE_SAVE_INTERVAL,
    BASELINE_STORAGE_VERSION,
    CONF_BASELINE_WINDOW_HOURS,
    CONF_ENTER_SCORE,
    CONF_EXIT_SCORE,
    CONF_FREEZE_HOLD_SECONDS,
    CONF_HOLD_SECONDS,
    CONF_K,
    CONF_SUPPORT_TAU_S,
    DEFAULT_PASSWORD,
    DOMAIN,
    PLATFORMS,
    STORE_PRUNE_INTERVAL,
)
from .coordinator import SmartLD2410Coordinator
from .store import FrameStore, default_db_path

_LOGGER = logging.getLogger(__name__)


@dataclass
class SmartLD2410RuntimeData:
    """Everything a loaded config entry needs to reach on unload/reconfigure."""

    coordinator: SmartLD2410Coordinator
    client: LD2410Client
    baseline_store: Store[dict[str, Any]]


type SmartLD2410ConfigEntry = ConfigEntry[SmartLD2410RuntimeData]


# -- Shared FrameStore lifecycle (refcounted across config entries) ----------


@dataclass
class _SharedStore:
    """The one FrameStore for the whole integration, plus its refcount."""

    store: FrameStore
    refcount: int
    prune_unsub: CALLBACK_TYPE


_DATA_SHARED_STORE = "shared_store"
_DATA_SHARED_STORE_LOCK = "shared_store_lock"


def _shared_store_lock(hass: HomeAssistant) -> asyncio.Lock:
    """Return the lock guarding shared-store creation/teardown.

    Created synchronously (no await between the check and the insert) so that
    config entries set up concurrently all end up with the same lock.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    lock: asyncio.Lock = domain_data.setdefault(_DATA_SHARED_STORE_LOCK, asyncio.Lock())
    return lock


async def _async_get_shared_store(hass: HomeAssistant) -> FrameStore:
    """Return the integration's single FrameStore, creating it on first use."""
    lock = _shared_store_lock(hass)
    async with lock:
        domain_data = hass.data.setdefault(DOMAIN, {})
        shared: _SharedStore | None = domain_data.get(_DATA_SHARED_STORE)
        if shared is None:
            db_path = default_db_path(hass.config.config_dir)
            store = await hass.async_add_executor_job(FrameStore, db_path)
            await hass.async_add_executor_job(store.start)

            async def _async_prune(_now: Any) -> None:
                await hass.async_add_executor_job(_prune_store, store)

            prune_unsub = async_track_time_interval(
                hass, _async_prune, STORE_PRUNE_INTERVAL
            )
            shared = _SharedStore(store=store, refcount=0, prune_unsub=prune_unsub)
            domain_data[_DATA_SHARED_STORE] = shared
        shared.refcount += 1
        return shared.store


async def _async_release_shared_store(hass: HomeAssistant) -> None:
    """Drop a reference to the shared store, closing it once unused."""
    lock = _shared_store_lock(hass)
    async with lock:
        domain_data: dict[str, Any] | None = hass.data.get(DOMAIN)
        if domain_data is None:
            return
        shared: _SharedStore | None = domain_data.get(_DATA_SHARED_STORE)
        if shared is None:
            return
        shared.refcount -= 1
        if shared.refcount > 0:
            return
        shared.prune_unsub()
        await hass.async_add_executor_job(shared.store.stop)
        domain_data.pop(_DATA_SHARED_STORE, None)


def _prune_store(store: FrameStore) -> None:
    """Run the daily retention prune (blocking; call via executor)."""
    store.prune(now_utc=time.time())


def _register_sensor_row(
    db_path: Path, sensor_id: str, name: str, room: str | None
) -> None:
    """Upsert this sensor's row into the store's `sensors` table (blocking)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO sensors (sensor_id, name, room) VALUES (?, ?, ?) "
            "ON CONFLICT(sensor_id) DO UPDATE SET name = excluded.name, "
            "room = excluded.room",
            (sensor_id, name, room),
        )
        conn.commit()
    finally:
        conn.close()


# -- DetectorConfig <-> options -----------------------------------------------


def _detector_config_from_options(options: Mapping[str, Any]) -> DetectorConfig:
    """Build a DetectorConfig from entry.options, falling back to defaults."""
    defaults = DetectorConfig()
    window_hours = options.get(
        CONF_BASELINE_WINDOW_HOURS, defaults.baseline_window_s / 3600
    )
    return DetectorConfig(
        k=options.get(CONF_K, defaults.k),
        baseline_window_s=window_hours * 3600,
        enter_score=options.get(CONF_ENTER_SCORE, defaults.enter_score),
        exit_score=options.get(CONF_EXIT_SCORE, defaults.exit_score),
        hold_s=options.get(CONF_HOLD_SECONDS, defaults.hold_s),
        freeze_hold_s=options.get(CONF_FREEZE_HOLD_SECONDS, defaults.freeze_hold_s),
        min_mad=defaults.min_mad,
        support_tau_s=options.get(CONF_SUPPORT_TAU_S, defaults.support_tau_s),
    )


def _restore_baseline(
    data: dict[str, Any] | None, config: DetectorConfig
) -> BaselineModel | None:
    """Restore a persisted baseline if it exists and matches the config window."""
    if data is None:
        return None
    try:
        if float(data["window_s"]) != config.baseline_window_s:
            return None
        return BaselineModel.from_dict(data)
    except (KeyError, TypeError, ValueError):
        _LOGGER.warning("Discarding incompatible persisted baseline", exc_info=True)
        return None


# -- Setup / unload ------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: SmartLD2410ConfigEntry) -> bool:
    """Set up Smart LD2410 from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"Could not find Smart LD2410 device with address {address}"
        )

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        identifiers={(DOMAIN, address)},
        name=entry.title,
        manufacturer="HiLink",
        model="LD2410",
    )

    store = await _async_get_shared_store(hass)
    try:
        await _async_setup_entry_with_store(
            hass, entry, address, ble_device, device_entry, store
        )
    except Exception:
        # Anything below can fail (and be retried); never leak the reference.
        await _async_release_shared_store(hass)
        raise
    return True


async def _async_setup_entry_with_store(
    hass: HomeAssistant,
    entry: SmartLD2410ConfigEntry,
    address: str,
    ble_device: BLEDevice,
    device_entry: dr.DeviceEntry,
    store: FrameStore,
) -> None:
    """Finish setup once the shared store reference has been acquired."""
    room = None
    if device_entry.area_id:
        area = ar.async_get(hass).async_get_area(device_entry.area_id)
        room = area.name if area is not None else None
    await hass.async_add_executor_job(
        _register_sensor_row, store.db_path, address, entry.title, room
    )

    config = _detector_config_from_options(entry.options)

    baseline_store: Store[dict[str, Any]] = Store(
        hass, BASELINE_STORAGE_VERSION, f"{DOMAIN}.baseline_{address}"
    )
    baseline_data = await baseline_store.async_load()
    baseline = _restore_baseline(baseline_data, config)

    detector = Detector(config, baseline=baseline)
    coordinator = SmartLD2410Coordinator(hass, entry, detector, store, address)

    def _lookup_ble_device() -> BLEDevice | None:
        """Re-resolve the freshest connectable BLEDevice for this address.

        Called by the client before each (re)connect attempt so it always
        routes through whichever bluetooth adapter/proxy currently has the
        best connection, rather than staying pinned to the adapter that
        happened to be current at setup time.
        """
        return bluetooth.async_ble_device_from_address(hass, address, connectable=True)

    password = entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
    client = LD2410Client(
        ble_device,
        coordinator.async_on_frame,
        coordinator.async_on_availability,
        password.encode("ascii"),
        ble_device_lookup=_lookup_ble_device,
    )

    entry.runtime_data = SmartLD2410RuntimeData(
        coordinator=coordinator, client=client, baseline_store=baseline_store
    )

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Hand a fresh BLEDevice reference to the client on adverts."""
        client.set_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            BluetoothCallbackMatcher({ADDRESS: address}),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    async def _async_save_baseline(_now: Any = None) -> None:
        await baseline_store.async_save(detector.baseline.to_dict())

    entry.async_on_unload(
        async_track_time_interval(hass, _async_save_baseline, BASELINE_SAVE_INTERVAL)
    )

    async def _async_options_updated(
        hass: HomeAssistant, entry: SmartLD2410ConfigEntry
    ) -> None:
        """Rebuild the DetectorConfig in place; the baseline is untouched."""
        coordinator.reconfigure(_detector_config_from_options(entry.options))
        baseline_store.async_delay_save(lambda: detector.baseline.to_dict(), delay=1.0)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(
        hass, client.start(), f"{DOMAIN}-{address}-client"
    )


async def async_unload_entry(hass: HomeAssistant, entry: SmartLD2410ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime_data = entry.runtime_data
        await runtime_data.client.stop()
        await runtime_data.baseline_store.async_save(
            runtime_data.coordinator.detector.baseline.to_dict()
        )
        await _async_release_shared_store(hass)
    return unload_ok
