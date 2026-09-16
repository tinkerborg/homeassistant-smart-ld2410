"""Bounded threshold hysteresis follow-up to experiment 21.

Labels are evaluation only.  Inference uses bathroom-sensor gates 2--8,
causal background tracking, motion threshold 40, tau 15 s, no departure
timer, signed retention, or ML.  The production integration is untouched.
"""
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "exp21", HERE.parent / "21-component-retention" / "analyze.py"
)
e21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e21)


def replay(t, move, still, tau=15.0, bar=40.0, on=0.4, off=0.4):
    """Replay one fixture, with single-threshold mode delegated to exp. 21."""
    if on == off:
        return e21.replay(t, move, still, tau=tau, bar=bar, retain=on)

    m, s = move[:, 2:9], still[:, 2:9]
    background = s[0].copy()
    h = None
    active = np.zeros(len(t), bool)
    score = np.zeros(len(t))
    residual = np.zeros_like(s)
    for i in range(len(t)):
        dt = 0.0 if i == 0 else max(0.0, float(t[i] - t[i - 1]))
        if dt > 0.55:
            h = None
            background = s[i].copy()
        r = np.maximum(s[i] - background, 0.0)
        residual[i] = r
        strong = m[i].max() >= bar
        candidate = r * (m[i] / max(float(m[i].max()), 1.0))
        if strong and np.dot(candidate, candidate) >= 1.0:
            if h is None or np.dot(candidate, candidate) > np.dot(h, h):
                h = candidate.copy()
        if h is not None:
            score[i] = float(np.dot(r, h) / np.dot(h, h))
            active[i] = score[i] >= (off if active[i - 1] else on)
            if not active[i]:
                h = None
        if h is None:
            background += (1 - np.exp(-dt / tau)) * (s[i] - background)
    return active, score, residual


def assess(f, active):
    rates = {c: e21.b.rate(active, e21.b.mask(f, c)) for c in ("IN", "TW", "EMPTY")}
    visits = []
    for c, a, z in f.spans:
        if c != "IN":
            continue
        q = (f.ts >= a) & (f.ts < z)
        idx = np.flatnonzero(q)
        if not len(idx):
            continue
        on_idx = idx[active[idx]]
        post = np.flatnonzero((f.ts >= z) & (f.ts < z + 10))
        off_idx = post[~active[post]]
        missing = e21.b.run_stats(~active, f.ts, q)
        visits.append({
            "start": float(a), "end": float(z), "frames": int(len(idx)),
            "positive_frames": int(active[idx].sum()),
            "missing_fraction": float(1.0 - active[idx].mean()),
            "within_visit_dropout_runs": int(missing["runs"]),
            "longest_dropout_s": float(missing["longest_span_s"]),
            "first_on_after_label_s": float(f.ts[on_idx[0]] - a) if len(on_idx) else None,
            "on_at_last_frame": bool(active[idx[-1]]),
            "first_off_after_exit_label_s": float(f.ts[off_idx[0]] - z) if len(off_idx) else None,
            "positive_frames_in_next_10s": int(active[post].sum()),
        })
    return {"rates": rates, "visits": visits}


CONFIGS = {
    "baseline_on0.4_off0.4": (0.4, 0.4),
    "hysteresis_on0.7_off0.3": (0.7, 0.3),
    "control_on0.3_off0.3": (0.3, 0.3),
    "control_on0.7_off0.4": (0.7, 0.4),
}


def main():
    fixtures = e21.b.fixtures()
    out = {name: {} for name in CONFIGS}
    for f in fixtures:
        for name, (on, off) in CONFIGS.items():
            state, score, residual = replay(f.ts, f.move, f.still, on=on, off=off)
            out[name][f.name] = assess(f, state)
            # The non-hysteretic baseline must be exactly experiment 21.
            if name == "baseline_on0.4_off0.4":
                old = e21.replay(f.ts, f.move, f.still, tau=15.0, bar=40.0, retain=0.4)
                assert all(np.array_equal(a, b) for a, b in zip((state, score, residual), old)), f.name

    # Every configuration is causal on a recorded prefix, including the new state machine.
    f = e21.b.new_fixture("labeled-walk-0915.db")
    n = len(f.ts) - 700
    for name, (on, off) in CONFIGS.items():
        full = replay(f.ts, f.move, f.still, on=on, off=off)
        prefix = replay(f.ts[:n], f.move[:n], f.still[:n], on=on, off=off)
        for x, y in zip(full, prefix):
            assert np.array_equal(x[:n], y), name

    (HERE / "results.json").write_text(json.dumps(out, indent=2) + "\n")
    with (HERE / "results.txt").open("w") as fp:
        for name in CONFIGS:
            fp.write(name + "\n")
            for fixture, result in out[name].items():
                rates = result["rates"]
                fp.write("  %s IN=%s TW=%s EMPTY=%s\n" % (
                    fixture,
                    "--" if rates["IN"] is None else f"{rates['IN']:.6f}",
                    "--" if rates["TW"] is None else f"{rates['TW']:.6f}",
                    "--" if rates["EMPTY"] is None else f"{rates['EMPTY']:.6f}"))
                for visit in result["visits"]:
                    fp.write("    visit frames=%d missing=%.6f dropout_runs=%d longest_dropout_s=%.6f entry=%s exit=%s\n" % (
                        visit["frames"], visit["missing_fraction"], visit["within_visit_dropout_runs"],
                        visit["longest_dropout_s"], visit["first_on_after_label_s"],
                        visit["first_off_after_exit_label_s"]))
    print("Exact experiment 21 baseline check passed for all fixtures.")
    print("Causal prefix check passed for all configurations.")
    for name in CONFIGS:
        print(name)
        for fixture, result in out[name].items():
            r = result["rates"]
            print(f"  {fixture}: IN={r['IN']} TW={r['TW']} EMPTY={r['EMPTY']}")


if __name__ == "__main__":
    main()
