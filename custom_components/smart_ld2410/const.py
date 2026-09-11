"""Constants for the Smart LD2410 integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

from . import store as _store
from .algo.types import GATE_SPACING_M, DetectorConfig  # noqa: F401

DOMAIN = "smart_ld2410"

# Advertised by the LD2410 radar regardless of the vendor-set device name.
LD2410_SERVICE_UUID = "0000af30-0000-1000-8000-00805f9b34fb"

# The LD2410 ships with this bluetooth password; most units are never
# reconfigured to a different one.
DEFAULT_PASSWORD = "HiLink"

# LD2410 BLE passwords are always exactly 6 ASCII characters.
PASSWORD_LENGTH = 6

# Platforms are forwarded from here as they're implemented.
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
]

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

# Cap on the smart_ld2410_features_v1 dispatcher signal (contract §1.2: <=2 Hz).
FEATURES_PUSH_INTERVAL_S = 0.5
FEATURES_SCHEMA_VERSION = 1
SIGNAL_FEATURES_V1 = "smart_ld2410_features_v1"

# HA bus event fired at detection-scope episode close (contract §1.3).
EVENT_EPISODE = "smart_ld2410_episode"

# `events` table kind for a learned energy-ceiling boundary change (spec 21
# §3). Gate-class transitions use the new class name as their kind; the
# boundary is not a class, so it gets its own.
EVENT_KIND_BOUNDARY = "boundary_gate"

# `mode` attribute reported on the occupancy binary_sensor and the feature
# stream, derived from DetectorOutput.baseline_ready (contract §1.1, §1.2).
MODE_PASSTHROUGH = "passthrough"
MODE_LEARNED = "learned"

# `events` table kind for a ground-truth label change.
EVENT_KIND_LABEL = "label"

# Ground-truth label select entity options.
LABEL_NONE = "none"
LABEL_OPTIONS: tuple[str, ...] = (
    LABEL_NONE,
    "toilet",
    "stove",
    "island",
    "hall-walk-by",
    "empty",
)

# Options flow / DetectorConfig knobs.
CONF_K = "k"
CONF_BASELINE_WINDOW_HOURS = "baseline_window_hours"
CONF_ENTER_SCORE = "enter_score"
CONF_EXIT_SCORE = "exit_score"
CONF_HOLD_SECONDS = "hold_seconds"
CONF_FREEZE_HOLD_SECONDS = "freeze_hold_seconds"
CONF_SUPPORT_TAU_S = "support_tau_s"

# Phase 2 dwell-character classification knobs (spec 20 §6), diagnostic-tier.
CONF_T_DWELL_S = "t_dwell_s"
CONF_T_BRIEF_S = "t_brief_s"
CONF_N_BLEED_MIN = "n_bleed_min"
CONF_N_PORTAL_MIN = "n_portal_min"
CONF_PORTAL_LEAD_FRAC = "portal_lead_frac"
CONF_LEAD_WINDOW_S = "lead_window_s"
CONF_STATS_HALF_LIFE_DAYS = "stats_half_life_days"
CONF_MAX_GATE = "max_gate"

# Phase 2 energy-ceiling boundary knobs (spec 21 §4), diagnostic-tier.
# CONF_CEILING_ENABLED gates only the *suppression*: the statistics and the
# published boundary_gate are unconditional (spec 21 §5).
CONF_CEILING_ENABLED = "ceiling_enabled"
CONF_CEIL_DROP = "ceil_drop"
CONF_N_CEIL_MIN = "n_ceil_min"
CONF_CEIL_SAT = "ceil_sat"
CONF_BOUNDARY_CONFIRM_DAYS = "boundary_confirm_days"

# Phase 2 episode energy floor (spec 23 §3), diagnostic-tier.
CONF_ENERGY_FLOOR = "energy_floor"

# Phase 2 arrival-gated entry (spec 22 §5), diagnostic-tier.
CONF_ARRIVAL_FRAC = "arrival_frac"
CONF_ARRIVAL_MIN_FRAMES = "arrival_min_frames"

# Retention knobs (contract §2), diagnostic-tier. Defaults sourced from
# store.py so it stays the single source of truth for retention defaults.
CONF_RAW_RETENTION_DAYS = "raw_retention_days"
CONF_SUMMARY_RETENTION_DAYS = "summary_retention_days"
DEFAULT_RAW_RETENTION_DAYS = _store.DEFAULT_RAW_RETENTION_DAYS
DEFAULT_SUMMARY_RETENTION_DAYS = _store.DEFAULT_SUMMARY_RETENTION_DAYS

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
DEFAULT_T_DWELL_S = _DETECTOR_DEFAULTS.t_dwell_s
DEFAULT_T_BRIEF_S = _DETECTOR_DEFAULTS.t_brief_s
DEFAULT_N_BLEED_MIN = _DETECTOR_DEFAULTS.n_bleed_min
DEFAULT_N_PORTAL_MIN = _DETECTOR_DEFAULTS.n_portal_min
DEFAULT_PORTAL_LEAD_FRAC = _DETECTOR_DEFAULTS.portal_lead_frac
DEFAULT_LEAD_WINDOW_S = _DETECTOR_DEFAULTS.lead_window_s
DEFAULT_STATS_HALF_LIFE_DAYS = _DETECTOR_DEFAULTS.stats_half_life_days
DEFAULT_MAX_GATE = _DETECTOR_DEFAULTS.max_gate
DEFAULT_CEILING_ENABLED = _DETECTOR_DEFAULTS.ceiling_enabled
DEFAULT_CEIL_DROP = _DETECTOR_DEFAULTS.ceil_drop
DEFAULT_N_CEIL_MIN = _DETECTOR_DEFAULTS.n_ceil_min
DEFAULT_CEIL_SAT = _DETECTOR_DEFAULTS.ceil_sat
DEFAULT_BOUNDARY_CONFIRM_DAYS = _DETECTOR_DEFAULTS.boundary_confirm_days
DEFAULT_ENERGY_FLOOR = _DETECTOR_DEFAULTS.energy_floor
DEFAULT_ARRIVAL_FRAC = _DETECTOR_DEFAULTS.arrival_frac
DEFAULT_ARRIVAL_MIN_FRAMES = _DETECTOR_DEFAULTS.arrival_min_frames
