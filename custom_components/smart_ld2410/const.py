"""Constants for the Smart LD2410 integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

from .algo.types import DetectorConfig

DOMAIN = "smart_ld2410"

# Advertised by the LD2410 radar regardless of the vendor-set device name.
LD2410_SERVICE_UUID = "0000af30-0000-1000-8000-00805f9b34fb"

# The LD2410 ships with this bluetooth password; most units are never
# reconfigured to a different one.
DEFAULT_PASSWORD = "HiLink"

# LD2410 BLE passwords are always exactly 6 ASCII characters.
PASSWORD_LENGTH = 6

# Platforms are forwarded from here as they're implemented.
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

# Moving/static sensitivity written to every gate by the "Set permissive
# thresholds" button. A low threshold makes the device flag nearly everything
# as occupied; its occupancy bit is only used host-side as a comparison
# baseline for the detector, which makes the real enter/exit decision, so the
# device's own thresholds should never be the thing filtering out signal.
PERMISSIVE_SENSITIVITY = 15

# Storage key/version for the persisted per-sensor baseline (see __init__.py).
BASELINE_STORAGE_VERSION = 1
BASELINE_SAVE_INTERVAL = timedelta(minutes=15)

# How often the shared FrameStore's retention prune runs.
STORE_PRUNE_INTERVAL = timedelta(hours=24)

# Cap on HA state writes from the push-mode coordinator; frames themselves
# are never throttled into the store or detector.
COORDINATOR_PUSH_INTERVAL_S = 1.0

# Options flow / DetectorConfig knobs.
CONF_K = "k"
CONF_BASELINE_WINDOW_HOURS = "baseline_window_hours"
CONF_ENTER_SCORE = "enter_score"
CONF_EXIT_SCORE = "exit_score"
CONF_HOLD_SECONDS = "hold_seconds"
CONF_FREEZE_HOLD_SECONDS = "freeze_hold_seconds"
CONF_SUPPORT_TAU_S = "support_tau_s"

# Defaults sourced from DetectorConfig itself so it stays the single source
# of truth for tuning defaults.
_DETECTOR_DEFAULTS = DetectorConfig()
DEFAULT_K = _DETECTOR_DEFAULTS.k
DEFAULT_BASELINE_WINDOW_HOURS = _DETECTOR_DEFAULTS.baseline_window_s / 3600
DEFAULT_ENTER_SCORE = _DETECTOR_DEFAULTS.enter_score
DEFAULT_EXIT_SCORE = _DETECTOR_DEFAULTS.exit_score
DEFAULT_HOLD_SECONDS = _DETECTOR_DEFAULTS.hold_s
DEFAULT_FREEZE_HOLD_SECONDS = _DETECTOR_DEFAULTS.freeze_hold_s
DEFAULT_SUPPORT_TAU_S = _DETECTOR_DEFAULTS.support_tau_s
