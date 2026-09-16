"""Focused tests for the causal motion anchor primitive."""

from custom_components.smart_ld2410.algo.presence.motion_anchor import MotionAnchor


FLOOR = [10.0] * 7
SPREAD = [2.0] * 7


def frame(ts, move=0.0, still=10.0):
    return (ts, [move] * 7, [still] * 7, FLOOR, SPREAD)


def test_weak_motion_does_not_start_anchor():
    anchor = MotionAnchor()
    assert not anchor.update(*frame(0.0, move=39.9, still=30.0))
    assert anchor.template is None


def test_anchor_retains_quiet_footprint_then_loses_it():
    anchor = MotionAnchor()
    assert anchor.update(*frame(0.0, move=60.0, still=30.0))
    assert anchor.update(*frame(0.1, move=0.0, still=30.0))
    assert not anchor.update(*frame(0.2, move=0.0, still=10.0))
    assert anchor.template is None


def test_only_usable_gates_are_considered():
    anchor = MotionAnchor()
    full_move = [0.0, 0.0, 60.0, 60.0, 60.0, 60.0, 60.0, 60.0, 60.0]
    full_still = [100.0, 100.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0]
    assert anchor.update(0.0, full_move, full_still, [10.0] * 9, [2.0] * 9)


def test_gap_and_backwards_timestamp_clear_template():
    anchor = MotionAnchor()
    assert anchor.update(*frame(1.0, move=60.0, still=30.0))
    assert not anchor.update(*frame(1.56, still=30.0))
    assert anchor.template is None
    assert anchor.update(*frame(2.0, move=60.0, still=30.0))
    assert not anchor.update(*frame(1.9, still=30.0))


def test_invalid_input_is_ignored_without_poisoning_state():
    anchor = MotionAnchor()
    assert anchor.update(*frame(0.0, move=60.0, still=30.0))
    assert not anchor.update(0.1, [60.0] * 6, [30.0] * 7, FLOOR, SPREAD)
    assert anchor.template is not None
    assert anchor.update(*frame(0.2, still=30.0))
    assert not anchor.update(0.3, [60.0] * 7, [30.0] * 7, FLOOR, [0.0] * 7)
    assert anchor.update(*frame(0.4, still=30.0))


def test_causal_result_does_not_depend_on_future_frame():
    anchor = MotionAnchor()
    assert anchor.update(*frame(0.0, move=60.0, still=30.0))
    assert anchor.score == 1.0
    assert anchor.update(*frame(0.1, still=30.0))
    assert anchor.score == 1.0


def test_motion_only_in_unusable_gates_cannot_anchor():
    anchor = MotionAnchor()
    assert not anchor.update(
        0.0, [100.0, 100.0] + [0.0] * 7, [100.0] * 9, [10.0] * 9, [2.0] * 9
    )
