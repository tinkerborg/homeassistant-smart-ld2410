"""Tests for custom_components.smart_ld2410.ble.protocol."""

from __future__ import annotations

from custom_components.smart_ld2410.ble import protocol
from custom_components.smart_ld2410.ble.protocol import (
    AckFrame,
    DeviceParams,
    FrameParser,
    UplinkFrame,
)

# --- Frame builders (mirror the wire layout byte-for-byte) -----------------


def _uplink_frame_bytes(data: bytes) -> bytes:
    return (
        protocol.UPLINK_HEADER
        + len(data).to_bytes(2, "little")
        + data
        + protocol.UPLINK_FOOTER
    )


def _cmd_frame_bytes(data: bytes) -> bytes:
    return (
        protocol.CMD_HEADER
        + len(data).to_bytes(2, "little")
        + data
        + protocol.CMD_FOOTER
    )


def _engineering_data(
    *,
    status: int = 0x03,
    move_distance: int = 120,
    move_energy: int = 88,
    static_distance: int = 90,
    static_energy: int = 77,
    detect_distance: int = 130,
    max_move_gate: int = 8,
    max_still_gate: int = 8,
    move_gate_energies: bytes = bytes(range(10, 19)),
    still_gate_energies: bytes = bytes(range(50, 59)),
    photo_sensor: int = 66,
    out_pin: int = 1,
) -> bytes:
    body = bytes([protocol.UPLINK_TYPE_ENGINEERING, 0xAA, status])
    body += move_distance.to_bytes(2, "little") + bytes([move_energy])
    body += static_distance.to_bytes(2, "little") + bytes([static_energy])
    body += detect_distance.to_bytes(2, "little")
    body += bytes([max_move_gate, max_still_gate])
    body += move_gate_energies
    body += still_gate_energies
    body += bytes([photo_sensor, out_pin])
    body += b"\x55\x00"
    return body


def _basic_data(
    *,
    status: int = 0x01,
    move_distance: int = 40,
    move_energy: int = 55,
    static_distance: int = 0,
    static_energy: int = 0,
    detect_distance: int = 40,
) -> bytes:
    body = bytes([protocol.UPLINK_TYPE_BASIC, 0xAA, status])
    body += move_distance.to_bytes(2, "little") + bytes([move_energy])
    body += static_distance.to_bytes(2, "little") + bytes([static_energy])
    body += detect_distance.to_bytes(2, "little")
    body += b"\x55\x00"
    return body


def _ack_data(word: int, status: int = 0, extra: bytes = b"") -> bytes:
    return word.to_bytes(2, "little") + status.to_bytes(2, "little") + extra


# --- Tests -------------------------------------------------------------


def test_engineering_frame_parses_all_fields() -> None:
    move_energies = bytes(range(10, 19))  # 9 distinct values
    still_energies = bytes(range(50, 59))  # 9 distinct values
    frame_bytes = _uplink_frame_bytes(
        _engineering_data(
            status=0x03,
            move_distance=120,
            move_energy=88,
            static_distance=90,
            static_energy=77,
            detect_distance=130,
            move_gate_energies=move_energies,
            still_gate_energies=still_energies,
            photo_sensor=66,
            out_pin=1,
        )
    )

    parser = FrameParser()
    results = parser.feed(frame_bytes)

    assert len(results) == 1
    frame = results[0]
    assert isinstance(frame, UplinkFrame)
    assert frame.engineering is True
    assert frame.moving is True
    assert frame.static is True
    assert frame.move_distance_cm == 120
    assert frame.move_energy == 88
    assert frame.static_distance_cm == 90
    assert frame.static_energy == 77
    assert frame.detect_distance_cm == 130
    assert frame.move_gate_energies == tuple(move_energies)
    assert frame.still_gate_energies == tuple(still_energies)
    assert frame.photo_sensor == 66
    assert frame.out_pin is True


def test_basic_frame_has_no_gate_arrays() -> None:
    frame_bytes = _uplink_frame_bytes(_basic_data(status=0x01))

    parser = FrameParser()
    results = parser.feed(frame_bytes)

    assert len(results) == 1
    frame = results[0]
    assert isinstance(frame, UplinkFrame)
    assert frame.engineering is False
    assert frame.moving is True
    assert frame.static is False
    assert frame.move_gate_energies is None
    assert frame.still_gate_energies is None
    assert frame.photo_sensor is None
    assert frame.out_pin is None


def test_fragmented_frame_parses_once_across_feeds() -> None:
    frame_bytes = _uplink_frame_bytes(_engineering_data())
    third = len(frame_bytes) // 3

    parser = FrameParser()
    results = []
    results += parser.feed(frame_bytes[:third])
    results += parser.feed(frame_bytes[third : 2 * third])
    assert results == []  # nothing complete yet
    results += parser.feed(frame_bytes[2 * third :])

    assert len(results) == 1
    assert isinstance(results[0], UplinkFrame)
    assert results[0].move_distance_cm == 120


def test_coalesced_frames_parse_in_order() -> None:
    engineering_bytes = _uplink_frame_bytes(_engineering_data())
    basic_bytes = _uplink_frame_bytes(_basic_data())
    ack_bytes = _cmd_frame_bytes(_ack_data(protocol.CMD_END_CONFIG | 0x0100))

    parser = FrameParser()
    results = parser.feed(engineering_bytes + basic_bytes + ack_bytes)

    assert len(results) == 3
    assert isinstance(results[0], UplinkFrame) and results[0].engineering is True
    assert isinstance(results[1], UplinkFrame) and results[1].engineering is False
    assert isinstance(results[2], AckFrame)
    assert results[2].command == (protocol.CMD_END_CONFIG | 0x0100)


def test_garbage_prefix_and_malformed_frame_are_skipped() -> None:
    good_frame = _uplink_frame_bytes(_basic_data(move_distance=77))

    malformed = bytearray(_uplink_frame_bytes(_basic_data(move_distance=99)))
    malformed[-1] ^= 0xFF  # corrupt the trailing footer byte

    garbage = b"\x00\x01\x02\x03"
    stream = garbage + bytes(malformed) + good_frame

    parser = FrameParser()
    results = parser.feed(stream)

    assert len(results) == 1
    assert isinstance(results[0], UplinkFrame)
    assert results[0].move_distance_cm == 77


def test_corrupted_length_does_not_swallow_following_frames() -> None:
    """A bad length field must not delete a span covering the next valid frame."""
    good_one = _uplink_frame_bytes(_basic_data(move_distance=11))
    good_two = _uplink_frame_bytes(_basic_data(move_distance=22))

    corrupt = bytearray(_uplink_frame_bytes(_basic_data(move_distance=99)))
    # Overstate the data length so the claimed frame runs into the next one.
    inflated = int.from_bytes(corrupt[4:6], "little") + 8
    corrupt[4:6] = inflated.to_bytes(2, "little")

    parser = FrameParser()
    results = parser.feed(bytes(corrupt) + good_one + good_two)

    assert [
        frame.move_distance_cm
        for frame in results
        if isinstance(frame, UplinkFrame)
    ] == [11, 22]


def test_spurious_header_with_huge_length_does_not_stall_parsing() -> None:
    """A bogus header claiming 65535 data bytes is dropped, not waited on."""
    good_one = _uplink_frame_bytes(_basic_data(move_distance=33))
    good_two = _uplink_frame_bytes(_basic_data(move_distance=44))
    spurious = protocol.UPLINK_HEADER + b"\xff\xff"

    parser = FrameParser()
    results = parser.feed(good_one + spurious + good_two)

    # Both real frames come out on this very feed; nothing is buffered waiting
    # for the 64KB the bogus length asked for.
    assert [
        frame.move_distance_cm
        for frame in results
        if isinstance(frame, UplinkFrame)
    ] == [33, 44]
    assert len(parser._buffer) < protocol._HEADER_LEN  # noqa: SLF001

    # Parsing keeps working straight afterwards.
    more = parser.feed(_uplink_frame_bytes(_basic_data(move_distance=55)))
    assert len(more) == 1
    assert isinstance(more[0], UplinkFrame)
    assert more[0].move_distance_cm == 55


def test_encode_command_matches_documented_layout() -> None:
    password_expected = (
        protocol.CMD_HEADER
        + b"\x08\x00"
        + b"\xa8\x00"
        + b"HiLink"
        + protocol.CMD_FOOTER
    )
    assert protocol.encode_password() == password_expected

    enable_config_expected = (
        protocol.CMD_HEADER
        + b"\x04\x00"
        + b"\xff\x00"
        + b"\x01\x00"
        + protocol.CMD_FOOTER
    )
    assert protocol.encode_enable_config() == enable_config_expected

    engineering_expected = (
        protocol.CMD_HEADER + b"\x02\x00" + b"\x62\x00" + protocol.CMD_FOOTER
    )
    assert protocol.encode_enable_engineering_mode() == engineering_expected

    end_config_expected = (
        protocol.CMD_HEADER + b"\x02\x00" + b"\xfe\x00" + protocol.CMD_FOOTER
    )
    assert protocol.encode_end_config() == end_config_expected

    set_sensitivity_expected = (
        protocol.CMD_HEADER
        + b"\x14\x00"
        + b"\x64\x00"
        + b"\x00\x00"
        + (3).to_bytes(4, "little")
        + b"\x01\x00"
        + (40).to_bytes(4, "little")
        + b"\x02\x00"
        + (40).to_bytes(4, "little")
        + protocol.CMD_FOOTER
    )
    assert (
        protocol.encode_set_gate_sensitivity(3, 40, 40) == set_sensitivity_expected
    )


def test_parse_params_ack_round_trip() -> None:
    move_sensitivities = bytes(range(1, 10))  # 9 distinct values
    still_sensitivities = bytes(range(20, 29))  # 9 distinct values
    data = (
        bytes([0xAA, 8, 8, 8])
        + move_sensitivities
        + still_sensitivities
        + (25).to_bytes(2, "little")
    )

    params = protocol.parse_params_ack(data)

    assert params == DeviceParams(
        max_gate=8,
        max_move_gate=8,
        max_still_gate=8,
        move_sensitivities=tuple(move_sensitivities),
        still_sensitivities=tuple(still_sensitivities),
        absence_delay_s=25,
    )
