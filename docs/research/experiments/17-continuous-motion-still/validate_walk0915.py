"""Frozen experiment-17 evaluation on the labeled-walk-0915 recording.

Training rows come only from the original experiment-17 bathroom fixtures.
The new file contributes no fitting, feature selection, sign selection, or
threshold selection. Labels are used only to define evaluation spans.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

import analyze as exp17

ROOT = Path(__file__).resolve().parents[4]
DB = ROOT / "tests" / "fixtures" / "recordings" / "labeled-walk-0915.db"
BATH = "D0:6E:81:D2:5D:A6"


def load_bath() -> tuple[exp17.data.Fixture, list[tuple[str, float, float]]]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select ts,move,still from frames where sensor_id=? order by ts", (BATH,)
    ).fetchall()
    ts = np.array([r[0] for r in rows], float)
    move = np.array([list(bytes(r[1])) for r in rows], float)
    still = np.array([list(bytes(r[2])) for r in rows], float)
    labels = con.execute("select person,room,ts_start,ts_end,note from labels order by ts_start").fetchall()
    # Conservative known-roster scope: the wife is explicitly in the kitchen;
    # the other person's explicit room is known. A segment is positive local
    # occupancy iff rob is explicitly in the bathroom. Otherwise it is a
    # known TW negative only while the wife is explicitly in the kitchen.
    wife_k = [(a, b) for p, room, a, b, _ in labels if p == "wife" and room == "kitchen"]
    rob = [(room, a, b) for p, room, a, b, _ in labels if p == "rob"]
    scope_a, scope_b = min(a for a, _ in wife_k), max(b for _, b in wife_k)
    cuts = {scope_a, scope_b}
    for room, a, b in rob:
        if b > scope_a and a < scope_b:
            cuts.update((max(a, scope_a), min(b, scope_b)))
    cuts = sorted(cuts)
    spans: list[tuple[str, float, float]] = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a <= 0.05:
            continue
        wife = any(x <= a + 0.01 and b <= y + 0.01 for x, y in wife_k)
        rob_rooms = [room for room, x, y in rob if x <= a + 0.01 and b <= y + 0.01]
        if not wife or not rob_rooms:
            continue
        cls = "IN" if "bathroom" in rob_rooms else "TW"
        # Merge adjacent bathroom-empty pieces (for example rob kitchen -> LR)
        # while never bridging an unknown/person-label gap.
        if spans and spans[-1][0] == cls and abs(spans[-1][2] - a) < 0.02:
            spans[-1] = (cls, spans[-1][1], b)
        else:
            spans.append((cls, a, b))
    fx = exp17.data.Fixture("labeled-walk-0915-bath", "d06e", ts, move, still, spans)
    return fx, spans


def old_rows(W: float) -> list[dict]:
    out = []
    for fx in exp17.data.all_fixtures().values():
        if fx.sensor != "d06e":
            continue
        for cls in ("IN", "TW"):
            for no, (_, a, b) in enumerate(fx.class_spans(cls)):
                out.extend(exp17.features(fx, cls, no, a, b, W))
    return out


def fit_score(train: list[dict], test: list[dict], keys: list[str]) -> np.ndarray:
    return exp17.rank_score(train, keys, train, test)


def auc(y: np.ndarray, s: np.ndarray) -> float:
    p=s[y==1]; n=s[y==0]
    if not len(p) or not len(n): return float("nan")
    return float(((p[:,None]>n[None,:]).sum()+0.5*(p[:,None]==n[None,:]).sum())/(len(p)*len(n)))


def print_strict(fx: exp17.data.Fixture, spans: list[tuple[str, float, float]], W: float, train: list[dict]) -> None:
    test=[]
    for no,(cls,a,b) in enumerate(spans):
        test.extend(r for r in exp17.features(fx, cls, no, a, b, W) if r["t"] < b)
    print(f"W={W:.0f}s strict windows={len(test)} IN={sum(r['cls']=='IN' for r in test)} TW={sum(r['cls']=='TW' for r in test)}")
    if not test or not {r["cls"] for r in test} == {"IN","TW"}:
        return
    y=np.array([r["cls"]=="IN" for r in test])
    for name,keys in (("baseline",exp17.BASE),("level",exp17.BASE+exp17.LEVEL),("first_difference",exp17.BASE+exp17.DIFF)):
        score=fit_score(train,test,keys)
        print(f"  {name} AUC={auc(y,score):.3f} score_IN=[{score[y].min():.3f},{score[y].max():.3f}] score_TW=[{score[~y].min():.3f},{score[~y].max():.3f}]")
    for no,(cls,a,b) in enumerate(spans):
        q=[r for r in test if r["span"]==no]
        if not q: print(f"  span {cls} {b-a:.1f}s windows=0 (too short for W={W:g}s)"); continue
        parts=[]
        for name,keys in (("base",exp17.BASE),("level",exp17.BASE+exp17.LEVEL),("diff",exp17.BASE+exp17.DIFF)):
            score=fit_score(train,q,keys)
            parts.append(f"{name}=[{score.min():.3f},{score.max():.3f}]")
        print(f"  span {cls} {b-a:.1f}s windows={len(q)} " + " ".join(parts))


def state_at(t: float, spans: list[tuple[str,float,float]]) -> str | None:
    for cls,a,b in spans:
        if a <= t < b: return cls
    return None


def timeline(fx: exp17.data.Fixture, spans: list[tuple[str,float,float]], W: float, train: list[dict]) -> None:
    # Diagnostic only: all-timeline windows can straddle truth transitions.
    known_a=min(a for _,a,_ in spans); known_b=max(b for _,_,b in spans)
    source_a=known_a-W
    allfx=exp17.data.Fixture(fx.name+"-all",fx.sensor,fx.ts,fx.move,fx.still,[("ALL",source_a,known_b)])
    test=exp17.features(allfx,"ALL",0,source_a,known_b,W)
    known=[r for r in test if state_at(r["t"],spans) is not None]
    for r in known: r["cls"]=state_at(r["t"],spans)
    boundaries=[x for _,a,b in spans for x in (a,b)]
    clean=[]; transition=[]
    for r in known:
        crossed=any(r["t"]-W < x <= r["t"] for x in boundaries)
        (transition if crossed else clean).append(r)
    print(f"W={W:.0f}s all-timeline known={len(known)} clean={len(clean)} transition={len(transition)}")
    for label,q in (("clean",clean),("all-known",known)):
        if {r["cls"] for r in q}!={"IN","TW"}: continue
        y=np.array([r["cls"]=="IN" for r in q]); parts=[]
        for name,keys in (("baseline",exp17.BASE),("level",exp17.BASE+exp17.LEVEL),("diff",exp17.BASE+exp17.DIFF)):
            s=fit_score(train,q,keys); parts.append(f"{name} AUC={auc(y,s):.3f}")
        print(f"  {label} " + " ".join(parts))


def main() -> None:
    fx,spans=load_bath()
    print(f"db={DB.name} sensor={BATH} frames={len(fx.ts)} duration={(fx.ts[-1]-fx.ts[0]):.1f}s")
    print("strict spans:")
    for cls,a,b in spans: print(f"  {cls} {a:.3f}-{b:.3f} ({b-a:.1f}s)")
    for W in (10.0,30.0):
        train=old_rows(W)
        print(f"OLD TRAIN W={W:.0f}s windows={len(train)}")
        print_strict(fx,spans,W,train)
        timeline(fx,spans,W,train)


if __name__ == "__main__": main()
