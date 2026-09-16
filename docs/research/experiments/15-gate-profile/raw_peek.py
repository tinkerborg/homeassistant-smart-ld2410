import numpy as np
import data

fx = data.all_fixtures()
np.set_printoptions(linewidth=200, formatter={"float": lambda v: f"{v:4.0f}"})

for sensor in ("d06e", "fd68"):
    for cls in ("IN", "TW", "EMPTY", "PET"):
        for f in fx.values():
            if f.sensor != sensor:
                continue
            for _, a, b in f.class_spans(cls):
                m = f.mask(a, b)
                i = np.flatnonzero(m)
                if len(i) < 40:
                    continue
                pick = i[np.linspace(0, len(i) - 1, 24).astype(int)]
                print(f"\n--- {sensor} {cls} {f.name} {data.clock(a)}-{data.clock(b)}")
                for j in pick:
                    print(f"  {data.clock(f.ts[j])} move", f.move[j], " still", f.still[j])
