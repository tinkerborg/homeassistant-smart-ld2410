"""4f streams: T5 (cat-exit splice on FD:68 seated) and T6 (bath two-person)."""
import sys, sqlite3
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2 import *   # noqa  (STREAM, go2, T, hm, DPRIME, CD2, ...)

c=sqlite3.connect('file:%s?mode=ro'%PROD,uri=True)
cf=sqlite3.connect('file:%s?mode=ro'%FIX,uri=True)
def A(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in c.execute(
      "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts",(a,b))]
def B(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in cf.execute(
      "select ts,move,still from frames where ts>=? and ts<? order by ts",(a,b))]

# ---- T5: FD:68 seated user + a synthetic near-band crossing (the "cat" exit).
# Source = the fixture's OWN real near-band walk frames (21:40:05-21:40:45, the
# re-entry through the near gates), per-gate MAX onto the seated span at 21:46.
# Same sensor/baseline, so the spliced frames really do read as near-band.
fd_warm, fd_body = STREAM['fd']
CROSS=[(ts,mv,st) for ts,mv,st in fd_body if T(21,40,5)<=ts<T(21,40,45)]
SPLICE_T=T(21,46,0)
def splice(body,over,t_at):
    out=[(ts,list(mv),list(st)) for ts,mv,st in body]
    i0=next(k for k,(ts,_,_) in enumerate(out) if ts>=t_at)
    for k,(_,mv,st) in enumerate(over):
        j=i0+k
        if j>=len(out): break
        for g in range(9):
            out[j][1][g]=max(out[j][1][g],mv[g]); out[j][2][g]=max(out[j][2][g],st[g])
    return out
STREAM['fdcat']=(fd_warm, splice(fd_body,CROSS,SPLICE_T))

# ---- T6: bathroom visit (A leaves 22:06:43) + a far-gate stayer (FD:68 seated), MAXed
WARMD=A(T(21,58)-6*3600,T(21,58))
base=A(T(21,58),T(22,12))
seat=B(T(21,44),T(21,55))
def tile(src,n):
    out=[]
    for _ in range(n): out+=src
    return out
def overlay(base,over):
    ov=tile(over,len(base)//max(len(over),1)+2)[:len(base)]
    return [(ts,[max(mv[g],ov[i][1][g]) for g in range(9)],
                [max(st[g],ov[i][2][g]) for g in range(9)])
            for i,(ts,mv,st) in enumerate(base)]
STREAM['two']=(WARMD, overlay(base,seat))
