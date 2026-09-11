"""Pure parsing/encoding for the HLK-LD2410 BLE protocol.

This module must not import bleak, homeassistant, or asyncio: it is plain
byte-level framing and struct math, independent of any transport.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Framing constants
# ---------------------------------------------------------------------------

UPLINK_HEADER = b"\xf4\xf3\xf2\xf1"
UPLINK_FOOTER = b"\xf8\xf7\xf6\xf5"
CMD_HEADER = b"\xfd\xfc\xfb\xfa"
CMD_FOOTER = b"\x04\x03\x02\x01"

_HEADER_LEN = 4
_LENGTH_FIELD_LEN = 2
_FOOTER_LEN = 4
_MIN_FRAME_LEN = _HEADER_LEN + _LENGTH_FIELD_LEN + _FOOTER_LEN

# Largest plausible data section. Real uplink frames top out around 40 bytes
# and the biggest ACK (read-parameters) around 30; anything beyond this is a
# corrupt length field, not a frame worth waiting for.
_MAX_DATA_LEN = 128

UPLINK_TYPE_ENGINEERING = 0x01
UPLINK_TYPE_BASIC = 0x02

# Data-section markers within an uplink frame.
_DATA_HEAD_BYTE = 0xAA
_DATA_TRAILER = b"\x55\x00"

# ---------------------------------------------------------------------------
# Command words
# ---------------------------------------------------------------------------

CMD_BLUETOOTH_PASSWORD = 0x00A8
CMD_ENABLE_CONFIG = 0x00FF
CMD_END_CONFIG = 0x00FE
CMD_ENABLE_ENGINEERING = 0x0062
CMD_READ_PARAMS = 0x0061
CMD_SET_SENSITIVITY = 0x0064

DEFAULT_PASSWORD = b"HiLink"

_ACK_STATUS_SUCCESS = 0

# Parameter words for CMD_SET_SENSITIVITY payload.
_PARAM_GATE = 0x0000
_PARAM_MOVE_SENSITIVITY = 0x0001
_PARAM_STATIC_SENSITIVITY = 0x0002


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UplinkFrame:
    """One parsed uplink (radar -> host) data frame."""

    engineering: bool
    moving: bool
    static: bool
    move_distance_cm: int
    move_energy: int
    static_distance_cm: int
    static_energy: int
    detect_distance_cm: int
    move_gate_energies: tuple[int, ...] | None
    still_gate_energies: tuple[int, ...] | None
    photo_sensor: int | None
    out_pin: bool | None


@dataclass(frozen=True, slots=True)
class AckFrame:
    """One parsed command-ACK frame."""

    command: int
    status: int
    data: bytes


@dataclass(frozen=True, slots=True)
class DeviceParams:
    """Decoded response of the read-parameters command."""

    max_gate: int
    max_move_gate: int
    max_still_gate: int
    move_sensitivities: tuple[int, ...]
    still_sensitivities: tuple[int, ...]
    absence_delay_s: int


# ---------------------------------------------------------------------------
# Frame parser
# ---------------------------------------------------------------------------


class FrameParser:
    """Accumulates notification bytes and extracts complete frames.

    Notifications from the LD2410 can fragment a frame across multiple
    packets or coalesce several frames into one; this class buffers
    everything fed to it and yields only frames that are complete and
    well-formed. Garbage bytes preceding a recognized header are discarded,
    and malformed frames are dropped in favor of resyncing on the next
    header rather than raising.
    """

    def __init__(self) -> None:
        """Initialize an empty accumulator buffer."""
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[UplinkFrame | AckFrame]:
        """Feed newly received bytes and return any newly completed frames."""
        self._buffer.extend(data)
        results: list[UplinkFrame | AckFrame] = []
        while True:
            frame = self._extract_one()
            if frame is None:
                break
            results.append(frame)
        return results

    def _extract_one(self) -> UplinkFrame | AckFrame | None:
        """Pop and parse a single frame from the buffer, if one is ready."""
        while True:
            uplink_idx = self._buffer.find(UPLINK_HEADER)
            cmd_idx = self._buffer.find(CMD_HEADER)
            candidates = [i for i in (uplink_idx, cmd_idx) if i != -1]
            if not candidates:
                # No header in the buffer. Keep only enough trailing bytes to
                # cover a header split across feeds; drop the rest as garbage.
                if len(self._buffer) > _HEADER_LEN - 1:
                    del self._buffer[: -(_HEADER_LEN - 1)]
                return None

            start = min(candidates)
            if start > 0:
                # Garbage before the next recognized header; discard it.
                del self._buffer[:start]
                continue

            is_uplink = uplink_idx == 0
            footer = UPLINK_FOOTER if is_uplink else CMD_FOOTER

            if len(self._buffer) < _HEADER_LEN + _LENGTH_FIELD_LEN:
                return None  # wait for more data

            data_len = int.from_bytes(
                self._buffer[_HEADER_LEN : _HEADER_LEN + _LENGTH_FIELD_LEN],
                "little",
            )
            if data_len > _MAX_DATA_LEN:
                # Implausible length: this "header" is corruption or noise.
                # Waiting for the claimed byte count would stall parsing (and
                # grow the buffer) indefinitely, so drop just the header bytes
                # and resync on the next one.
                del self._buffer[:_HEADER_LEN]
                continue

            frame_len = _MIN_FRAME_LEN + data_len
            if len(self._buffer) < frame_len:
                return None  # wait for more data

            frame_bytes = bytes(self._buffer[:frame_len])

            if not frame_bytes.endswith(footer):
                # Malformed frame: the length field can't be trusted either, so
                # consume only the header and resync on the next one rather
                # than deleting a span that may straddle a valid frame.
                del self._buffer[:_HEADER_LEN]
                continue

            payload = frame_bytes[
                _HEADER_LEN + _LENGTH_FIELD_LEN : _HEADER_LEN
                + _LENGTH_FIELD_LEN
                + data_len
            ]
            parsed = (
                _parse_uplink_payload(payload)
                if is_uplink
                else _parse_ack_payload(payload)
            )
            if parsed is None:
                # Malformed data section: drop the header and resync.
                del self._buffer[:_HEADER_LEN]
                continue

            del self._buffer[:frame_len]
            return parsed


def _parse_uplink_payload(payload: bytes) -> UplinkFrame | None:
    """Parse the data section of an uplink frame, or None if malformed."""
    if len(payload) < 2:
        return None
    frame_type = payload[0]
    if payload[1] != _DATA_HEAD_BYTE:
        return None
    if frame_type not in (UPLINK_TYPE_ENGINEERING, UPLINK_TYPE_BASIC):
        return None
    if not payload.endswith(_DATA_TRAILER):
        return None

    content = payload[2:-2]
    if len(content) < 9:
        return None

    status = content[0]
    moving = bool(status & 0x01)
    static = bool(status & 0x02)
    move_distance_cm = int.from_bytes(content[1:3], "little")
    move_energy = content[3]
    static_distance_cm = int.from_bytes(content[4:6], "little")
    static_energy = content[6]
    detect_distance_cm = int.from_bytes(content[7:9], "little")

    move_gate_energies: tuple[int, ...] | None = None
    still_gate_energies: tuple[int, ...] | None = None
    photo_sensor: int | None = None
    out_pin: bool | None = None

    engineering = frame_type == UPLINK_TYPE_ENGINEERING
    if engineering:
        idx = 9
        if len(content) < idx + 2:
            return None
        max_move_gate = content[idx]
        max_still_gate = content[idx + 1]
        idx += 2
        move_len = max_move_gate + 1
        still_len = max_still_gate + 1
        if len(content) < idx + move_len + still_len + 2:
            return None
        move_gate_energies = tuple(content[idx : idx + move_len])
        idx += move_len
        still_gate_energies = tuple(content[idx : idx + still_len])
        idx += still_len
        photo_sensor = content[idx]
        out_pin = bool(content[idx + 1])

    return UplinkFrame(
        engineering=engineering,
        moving=moving,
        static=static,
        move_distance_cm=move_distance_cm,
        move_energy=move_energy,
        static_distance_cm=static_distance_cm,
        static_energy=static_energy,
        detect_distance_cm=detect_distance_cm,
        move_gate_energies=move_gate_energies,
        still_gate_energies=still_gate_energies,
        photo_sensor=photo_sensor,
        out_pin=out_pin,
    )


def _parse_ack_payload(payload: bytes) -> AckFrame | None:
    """Parse the data section of a command-ACK frame, or None if malformed."""
    if len(payload) < 4:
        return None
    command = int.from_bytes(payload[0:2], "little")
    status = int.from_bytes(payload[2:4], "little")
    return AckFrame(command=command, status=status, data=payload[4:])


# ---------------------------------------------------------------------------
# Command encoders
# ---------------------------------------------------------------------------


def encode_command(word: int, payload: bytes = b"") -> bytes:
    """Encode a downlink command frame for the given command word."""
    body = word.to_bytes(2, "little") + payload
    return (
        CMD_HEADER + len(body).to_bytes(2, "little") + body + CMD_FOOTER
    )


def encode_password(password: bytes = DEFAULT_PASSWORD) -> bytes:
    """Encode the bluetooth-password command."""
    return encode_command(CMD_BLUETOOTH_PASSWORD, password)


def encode_enable_config() -> bytes:
    """Encode the enable-config-mode command."""
    return encode_command(CMD_ENABLE_CONFIG, (1).to_bytes(2, "little"))


def encode_end_config() -> bytes:
    """Encode the end-config-mode command."""
    return encode_command(CMD_END_CONFIG)


def encode_enable_engineering_mode() -> bytes:
    """Encode the enable-engineering-mode command."""
    return encode_command(CMD_ENABLE_ENGINEERING)


def encode_read_params() -> bytes:
    """Encode the read-parameters command."""
    return encode_command(CMD_READ_PARAMS)


def encode_set_gate_sensitivity(gate: int, moving: int, static: int) -> bytes:
    """Encode the set-gate-sensitivity command."""
    payload = (
        _PARAM_GATE.to_bytes(2, "little")
        + gate.to_bytes(4, "little")
        + _PARAM_MOVE_SENSITIVITY.to_bytes(2, "little")
        + moving.to_bytes(4, "little")
        + _PARAM_STATIC_SENSITIVITY.to_bytes(2, "little")
        + static.to_bytes(4, "little")
    )
    return encode_command(CMD_SET_SENSITIVITY, payload)


def parse_params_ack(data: bytes) -> DeviceParams:
    """Parse the data section of a read-parameters ACK (after the status word)."""
    if len(data) < 4 or data[0] != _DATA_HEAD_BYTE:
        raise ValueError("Malformed read-parameters ACK payload")
    max_gate = data[1]
    max_move_gate = data[2]
    max_still_gate = data[3]
    idx = 4
    gate_len = max_gate + 1
    if len(data) < idx + gate_len * 2 + 2:
        raise ValueError("Malformed read-parameters ACK payload")
    move_sensitivities = tuple(data[idx : idx + gate_len])
    idx += gate_len
    still_sensitivities = tuple(data[idx : idx + gate_len])
    idx += gate_len
    absence_delay_s = int.from_bytes(data[idx : idx + 2], "little")
    return DeviceParams(
        max_gate=max_gate,
        max_move_gate=max_move_gate,
        max_still_gate=max_still_gate,
        move_sensitivities=move_sensitivities,
        still_sensitivities=still_sensitivities,
        absence_delay_s=absence_delay_s,
    )
