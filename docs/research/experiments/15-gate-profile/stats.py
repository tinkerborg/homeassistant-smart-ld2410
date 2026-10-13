"""Per-frame gate-profile shape statistics."""

from __future__ import annotations

import numpy as np

STILL_GATES = np.arange(2, 9)
MOVE_GATES = np.arange(0, 9)

STAT_NAMES = [
    "mass",
    "near_frac",
    "centroid",
    "spread",
    "peak_gate",
    "fall1",
    "fall2",
    "n_gates",
    "deep_mass",
    "deep_frac",
    "lead_frac",
    "shoulder",
    "tail",
    "shoulder_sum",
    "g2",
    "g3",
    "g4",
    "g5",
    "g6",
    "cos_in",
    "cos_tw",
    "cos_margin",
]


def smooth(ts: np.ndarray, v: np.ndarray, window_s: float) -> np.ndarray:
    if window_s <= 0:
        return v
    out = np.empty_like(v)
    lo = 0
    csum = np.cumsum(np.vstack([np.zeros((1, v.shape[1])), v]), axis=0)
    for i in range(len(ts)):
        while ts[i] - ts[lo] > window_s:
            lo += 1
        out[i] = (csum[i + 1] - csum[lo]) / (i + 1 - lo)
    return out


def residual(v: np.ndarray, floor: np.ndarray | None, gates: np.ndarray) -> np.ndarray:
    r = v[:, gates]
    if floor is not None:
        r = r - floor[gates]
    return np.clip(r, 0, None)


def profile_stats(r: np.ndarray, gates: np.ndarray, near: int) -> dict[str, np.ndarray]:
    total = r.sum(axis=1)
    safe = np.where(total > 0, total, 1.0)
    idx = gates.astype(float)
    near_mask = gates <= near
    deep_mask = gates >= near + 2

    centroid = (r * idx).sum(axis=1) / safe
    var = (r * (idx[None, :] - centroid[:, None]) ** 2).sum(axis=1) / safe
    peak = r.argmax(axis=1)
    padded = np.hstack([r, np.zeros((len(r), 2))])
    peak_val = np.where(r.max(axis=1) > 0, r.max(axis=1), 1.0)
    rows = np.arange(len(r))

    out = {
        "mass": total,
        "near_frac": r[:, near_mask].sum(axis=1) / safe,
        "centroid": np.where(total > 0, centroid, np.nan),
        "spread": np.where(total > 0, np.sqrt(var), np.nan),
        "peak_gate": np.where(total > 0, gates[peak], np.nan).astype(float),
        "fall1": np.where(total > 0, padded[rows, peak + 1] / peak_val, np.nan),
        "fall2": np.where(total > 0, padded[rows, peak + 2] / peak_val, np.nan),
        "n_gates": (r > 5).sum(axis=1).astype(float),
        "deep_mass": r[:, deep_mask].sum(axis=1),
        "deep_frac": r[:, deep_mask].sum(axis=1) / safe,
    }
    for g in (2, 3, 4, 5, 6):
        out[f"g{g}"] = r[:, gates == g][:, 0]
    core = np.maximum(r[:, gates == 2][:, 0], r[:, gates == 3][:, 0])
    core_safe = np.where(core > 0, core, np.nan)
    g2 = r[:, gates == 2][:, 0]
    g3 = r[:, gates == 3][:, 0]
    pair = g2 + g3
    out["lead_frac"] = np.where(pair > 0, g2 / np.where(pair > 0, pair, 1.0), np.nan)
    out["shoulder"] = r[:, gates == 4][:, 0] / core_safe
    out["tail"] = r[:, gates == 5][:, 0] / core_safe
    out["shoulder_sum"] = (r[:, gates == 4][:, 0] + r[:, gates == 5][:, 0]) / core_safe
    return out


def cosine(r: np.ndarray, template: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(r, axis=1) * np.linalg.norm(template)
    return np.where(n > 0, r @ template / np.where(n > 0, n, 1.0), np.nan)


def compute(v: np.ndarray, ts: np.ndarray, floor: np.ndarray | None, channel: str,
            window_s: float, templates: dict[str, np.ndarray] | None) -> dict[str, np.ndarray]:
    gates = STILL_GATES if channel == "still" else MOVE_GATES
    near = 3
    r = residual(smooth(ts, v, window_s), floor, gates)
    out = profile_stats(r, gates, near)
    if templates:
        out["cos_in"] = cosine(r, templates["IN"])
        out["cos_tw"] = cosine(r, templates["TW"])
        out["cos_margin"] = out["cos_in"] - out["cos_tw"]
    return out
