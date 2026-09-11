"""BLE transport for the HLK-LD2410 radar: connect, authenticate, stream."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from ..algo.types import Frame
from . import protocol
from .errors import AuthenticationError, CommandError
from .protocol import AckFrame, DeviceParams, FrameParser, UplinkFrame

_LOGGER = logging.getLogger(__name__)

NOTIFY_CHARACTERISTIC_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_CHARACTERISTIC_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"

_COMMAND_TIMEOUT_S = 5.0
_RECONNECT_INITIAL_DELAY_S = 1.0
_RECONNECT_MAX_DELAY_S = 60.0
_INTER_COMMAND_DELAY_S = 0.1


class LD2410Client:
    """Maintains a persistent BLE connection to one LD2410 radar."""

    def __init__(
        self,
        ble_device: BLEDevice,
        on_frame: Callable[[Frame], None],
        on_availability: Callable[[bool], None],
        password: bytes = protocol.DEFAULT_PASSWORD,
        ble_device_lookup: Callable[[], BLEDevice | None] | None = None,
    ) -> None:
        """Initialize the client. Does not connect; call start() for that.

        ``ble_device_lookup``, if given, is called synchronously before each
        connection attempt to fetch the freshest connectable ``BLEDevice`` for
        this address (e.g. HA's ``bluetooth.async_ble_device_from_address``,
        which is itself a sync callback despite the ``async_`` prefix). This
        lets the client route through whichever bluetooth adapter/proxy is
        currently best-connected, instead of being pinned to the device
        object it was constructed with. When the lookup is absent or returns
        None, the last-known ``_ble_device`` is used instead.
        """
        self._ble_device = ble_device
        self._on_frame = on_frame
        self._on_availability = on_availability
        self._password = password
        self._ble_device_lookup = ble_device_lookup

        self._client: BleakClientWithServiceCache | None = None
        self._parser = FrameParser()
        self._command_lock = asyncio.Lock()
        self._pending_acks: dict[int, asyncio.Future[AckFrame]] = {}

        self._stopping = False
        self._available = False
        self._expected_disconnect = False
        self._reconnect_task: asyncio.Task[None] | None = None

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice reference (called on bluetooth callbacks)."""
        self._ble_device = ble_device

    async def start(self) -> None:
        """Begin connecting to the device in the background.

        The initial connection goes through the same backoff loop as a
        reconnect, so a device that is out of range at setup time simply stays
        unavailable and keeps retrying instead of never coming back.
        """
        self._stopping = False
        self._ensure_reconnect_task()

    async def stop(self) -> None:
        """Disconnect cleanly and stop reconnecting."""
        self._stopping = True
        task, self._reconnect_task = self._reconnect_task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._fail_pending_acks(ConnectionError("Client stopped"))
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            self._expected_disconnect = True
            await client.disconnect()

    async def read_params(self) -> DeviceParams:
        """Read the device's current gate/sensitivity configuration."""
        async with self._command_lock:
            await self._enter_config_mode_locked()
            try:
                ack = await self._send_command_locked(protocol.encode_read_params())
            finally:
                await self._exit_config_mode_locked()
        return protocol.parse_params_ack(ack.data)

    async def set_gate_sensitivity(self, gate: int, moving: int, static: int) -> None:
        """Set the moving/static sensitivity thresholds for one gate."""
        async with self._command_lock:
            await self._enter_config_mode_locked()
            try:
                await self._send_command_locked(
                    protocol.encode_set_gate_sensitivity(gate, moving, static)
                )
            finally:
                await self._exit_config_mode_locked()

    # -- Connection lifecycle -------------------------------------------------

    def _resolve_ble_device(self) -> BLEDevice:
        """Re-resolve the freshest connectable BLEDevice before an attempt.

        Falls back to the last-known device when there is no lookup, or the
        lookup can't find a currently-connectable device for this address.
        """
        if self._ble_device_lookup is not None:
            resolved = self._ble_device_lookup()
            if resolved is not None:
                self._ble_device = resolved
        return self._ble_device

    async def _connect_with_init(self) -> None:
        """Establish a connection and run the full init sequence."""
        self._expected_disconnect = False
        ble_device = self._resolve_ble_device()
        details = getattr(ble_device, "details", None)
        source = details.get("source") if isinstance(details, dict) else None
        _LOGGER.info(
            "%s: Connecting via %s (source=%s, details=%s)",
            ble_device.address,
            ble_device.name or ble_device.address,
            source,
            details,
        )
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.name or ble_device.address,
            self._on_disconnected,
            use_services_cache=True,
            ble_device_callback=self._resolve_ble_device,
        )
        self._client = client
        self._parser = FrameParser()

        try:
            await self._run_init_sequence()
        except AuthenticationError:
            _LOGGER.error(
                "%s: Authentication failed - check the configured password",
                self._ble_device.address,
                exc_info=True,
            )
            # Deliberate disconnect: bleak still fires the disconnected
            # callback, which must not spawn a competing reconnect loop.
            self._expected_disconnect = True
            self._client = None
            await client.disconnect()
            raise
        except Exception:
            _LOGGER.warning(
                "%s: Init sequence failed after connect",
                self._ble_device.address,
                exc_info=True,
            )
            # Deliberate disconnect: bleak still fires the disconnected
            # callback, which must not spawn a competing reconnect loop.
            self._expected_disconnect = True
            self._client = None
            await client.disconnect()
            raise

        _LOGGER.info("%s: Connected and initialized", self._ble_device.address)
        self._set_available(True)

    async def _run_init_sequence(self) -> None:
        """Subscribe, then password, enable config, engineering mode, end config.

        Command ACKs arrive on the notify characteristic, so the subscription
        must exist before the first command is sent or every ACK wait times out.
        """
        assert self._client is not None
        await self._client.start_notify(
            NOTIFY_CHARACTERISTIC_UUID, self._on_notify
        )

        async with self._command_lock:
            await self._send_command_locked(protocol.encode_password(self._password))
            await asyncio.sleep(_INTER_COMMAND_DELAY_S)
            await self._enter_config_mode_locked()
            try:
                await self._send_command_locked(
                    protocol.encode_enable_engineering_mode()
                )
            finally:
                await self._exit_config_mode_locked()

    def _on_disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Handle an unexpected (or deliberate) BLE disconnect."""
        self._fail_pending_acks(ConnectionError("Device disconnected"))
        self._set_available(False)
        if self._stopping or self._expected_disconnect:
            _LOGGER.debug("%s: Disconnected", self._ble_device.address)
            return
        _LOGGER.warning("%s: Disconnected unexpectedly", self._ble_device.address)
        self._ensure_reconnect_task()

    def _ensure_reconnect_task(self) -> None:
        """Start the reconnect loop unless one is already running."""
        if self._stopping:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """(Re)connect with exponential backoff until it succeeds or stop() runs.

        Also drives the very first connection attempt made by start().
        """
        delay = _RECONNECT_INITIAL_DELAY_S
        while not self._stopping:
            try:
                await self._connect_with_init()
                return
            except AuthenticationError:
                # A wrong password won't fix itself on the next attempt, so
                # don't hammer the device at the fast end of the backoff.
                delay = _RECONNECT_MAX_DELAY_S
                _LOGGER.debug(
                    "%s: Reconnect attempt failed (authentication), retrying in %.1fs",
                    self._ble_device.address,
                    delay,
                )
                await asyncio.sleep(delay)
            except (BleakError, TimeoutError, OSError, CommandError):
                _LOGGER.debug(
                    "%s: Reconnect attempt failed, retrying in %.1fs",
                    self._ble_device.address,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY_S)

    def _set_available(self, available: bool) -> None:
        if available != self._available:
            self._available = available
            self._on_availability(available)

    # -- Notification handling -------------------------------------------------

    def _on_notify(self, _characteristic: object, data: bytearray) -> None:
        """Handle an incoming BLE notification (may contain 0+ frames)."""
        ts_utc = time.time()
        ts_mono = time.monotonic()
        _LOGGER.debug("%s: RX %s", self._ble_device.address, bytes(data).hex())
        for frame in self._parser.feed(bytes(data)):
            if isinstance(frame, AckFrame):
                self._resolve_ack(frame)
            else:
                self._handle_uplink_frame(frame, ts_utc, ts_mono)

    def _handle_uplink_frame(
        self, uplink: UplinkFrame, ts_utc: float, ts_mono: float
    ) -> None:
        _LOGGER.debug("%s: Frame: %s", self._ble_device.address, uplink)
        if not uplink.engineering:
            return
        move_gates = uplink.move_gate_energies or ()
        still_gates = uplink.still_gate_energies or ()
        frame = Frame(
            ts_utc=ts_utc,
            ts_mono=ts_mono,
            move_gates=move_gates,
            still_gates=still_gates,
            target_distance_cm=uplink.detect_distance_cm,
            device_occupancy=uplink.moving or uplink.static,
        )
        self._on_frame(frame)

    def _resolve_ack(self, ack: AckFrame) -> None:
        future = self._pending_acks.pop(ack.command, None)
        if future is None:
            _LOGGER.debug(
                "%s: Unexpected ACK for command 0x%04X",
                self._ble_device.address,
                ack.command,
            )
            return
        if not future.done():
            future.set_result(ack)

    def _fail_pending_acks(self, error: Exception) -> None:
        pending, self._pending_acks = self._pending_acks, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(error)

    # -- Command send/ACK matching ---------------------------------------------

    async def _send_command_locked(self, frame: bytes) -> AckFrame:
        """Write a command frame and wait for its matching ACK.

        Caller must hold ``_command_lock``.
        """
        if self._client is None or not self._client.is_connected:
            raise ConnectionError("Not connected")
        word = int.from_bytes(frame[6:8], "little")
        ack_word = word | 0x0100
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AckFrame] = loop.create_future()
        self._pending_acks[ack_word] = future
        try:
            await self._client.write_gatt_char(
                WRITE_CHARACTERISTIC_UUID, frame, response=False
            )
            try:
                ack = await asyncio.wait_for(future, timeout=_COMMAND_TIMEOUT_S)
            except TimeoutError as err:
                raise TimeoutError(
                    f"No ACK for command 0x{word:04x} within {_COMMAND_TIMEOUT_S}s"
                ) from err
        finally:
            self._pending_acks.pop(ack_word, None)

        if ack.status != 0:
            if word == protocol.CMD_BLUETOOTH_PASSWORD:
                raise AuthenticationError(word, ack.status)
            raise CommandError(word, ack.status)
        return ack

    async def _enter_config_mode_locked(self) -> None:
        await self._send_command_locked(protocol.encode_enable_config())

    async def _exit_config_mode_locked(self) -> None:
        await self._send_command_locked(protocol.encode_end_config())
