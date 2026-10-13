"""Render the replacement-sensor recording with Pillow and NumPy."""

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DB = HERE.parents[3] / "tests/fixtures/recordings/living-room-continuous-occupancy-2026-09-16.db"
TZ = ZoneInfo("America/New_York")
SENSORS = {
    "Bathroom": ("D0:6E:81:D2:5D:A6", "binary_sensor.downstairs_bathroom_downstairs_bathroom_occupancy"),
    "Kitchen": ("B3:26:9E:EE:C5:11", "binary_sensor.kitchen_kitchen_occupancy"),
    "Living room": ("68:43:B2:C2:7C:4A", "binary_sensor.living_room_living_room_back_occupancy"),
}
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


F16, F20, F25, F34 = (font(s) for s in (16, 20, 25, 34))


def stamp(hms):
    return datetime.fromisoformat("2026-09-16 " + hms).replace(tzinfo=TZ).timestamp()


with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
    labels = con.execute("SELECT room,ts_start,ts_end FROM labels ORDER BY ts_start").fetchall()
    data = {}
    for name, (sensor, entity) in SENSORS.items():
        rows = con.execute("SELECT ts,move,still FROM frames WHERE sensor_id=? ORDER BY ts", (sensor,)).fetchall()
        states = con.execute("SELECT ts,state FROM states WHERE entity_id=? ORDER BY ts", (entity,)).fetchall()
        data[name] = (
            np.array([r[0] for r in rows]),
            np.array([list(r[1]) for r in rows], dtype=np.uint8),
            np.array([list(r[2]) for r in rows], dtype=np.uint8),
            np.array([r[0] for r in states]),
            np.array([r[1] == "on" for r in states], dtype=bool),
        )


def xcoord(ts, lo, hi, x0, width):
    return x0 + round((ts - lo) / (hi - lo) * width)


def heat_color(value):
    stops = ((0, (16, 13, 33)), (15, (49, 24, 94)), (35, (113, 35, 114)),
             (55, (188, 52, 91)), (75, (243, 115, 67)), (100, (255, 245, 177)))
    for (a, c0), (b, c1) in zip(stops, stops[1:]):
        if value <= b:
            f = (value - a) / (b - a)
            return tuple(round(u + (v - u) * f) for u, v in zip(c0, c1))
    return stops[-1][1]


LUT = [heat_color(i) for i in range(101)]


def heatmap(canvas, rows, lo, hi, box, mode="max"):
    ts, readings = rows
    x0, y0, width, height = box
    gates = range(2, 9)
    pix = np.zeros((height, width, 3), dtype=np.uint8)
    edges = np.linspace(lo, hi, width + 1)
    starts = np.searchsorted(ts, edges[:-1], side="left")
    ends = np.searchsorted(ts, edges[1:], side="left")
    for x in range(width):
        segment = readings[starts[x]:max(ends[x], starts[x] + 1), 2:9]
        if len(segment):
            vals = np.max(segment, axis=0) if mode == "max" else np.median(segment, axis=0)
        else:
            vals = np.zeros(7)
        for g, value in enumerate(vals):
            a = round(g * height / 7)
            b = round((g + 1) * height / 7)
            pix[a:b, x] = LUT[min(100, int(value))]
    canvas.paste(Image.fromarray(pix), (x0, y0))


def state_bar(draw, ts, states, lo, hi, box):
    x0, y0, width, height = box
    edge = np.linspace(lo, hi, width)
    indices = np.searchsorted(ts, edge, side="right") - 1
    for x, idx in enumerate(indices):
        on = bool(states[idx]) if idx >= 0 else False
        color = (35, 144, 112) if on else (212, 72, 83)
        draw.line((x0 + x, y0, x0 + x, y0 + height), fill=color)
    draw.rectangle((x0, y0, x0 + width, y0 + height), outline=(190, 198, 209), width=1)


def time_axis(draw, lo, hi, x0, width, y, every_s):
    first = int(lo // every_s + 1) * every_s
    for ts in np.arange(first, hi, every_s):
        x = xcoord(ts, lo, hi, x0, width)
        draw.line((x, y - 8, x, y), fill=(100, 111, 128), width=2)
        label = datetime.fromtimestamp(float(ts), TZ).strftime("%H:%M:%S" if every_s < 120 else "%H:%M")
        draw.text((x - 32, y + 5), label, fill=(43, 54, 70), font=F16)


def key(draw, y):
    for i, (label, color) in enumerate((("Kitchen", (236, 183, 65)), ("Walk past bathroom", (103, 161, 203)),
                                       ("In living room", (66, 167, 127)), ("Occupied", (35, 144, 112)),
                                       ("Vacant", (212, 72, 83)))):
        x = 180 + i * 315
        draw.rectangle((x, y, x + 20, y + 20), fill=color)
        draw.text((x + 28, y - 2), label, fill=(50, 62, 78), font=F20)


def draw_gate_labels(draw, y, height, x):
    for g in range(2, 9):
        cy = y + (g - 2 + .5) * height / 7
        draw.text((x, int(cy) - 9), str(g), fill=(79, 89, 102), font=F16)


def journey():
    lo, hi = stamp("11:38:40"), stamp("11:43:00")
    image = Image.new("RGB", (1920, 1080), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    draw.text((82, 35), "Kitchen → bathroom walk-by → living-room entry", fill=(25, 40, 57), font=F34)
    draw.text((85, 85), "Sept 16 · replacement living-room sensor · raw gate energy 0–100 and recorded occupancy", fill=(72, 83, 97), font=F20)
    key(draw, 128)
    x0, width = 180, 1660
    for row, (name, (ts, move, still, state_ts, state)) in enumerate(data.items()):
        top = 185 + row * 275
        draw.text((42, top + 80), name, fill=(26, 43, 58), font=F25)
        for label, arr, y in (("Motion", move, top + 10), ("Still", still, top + 100)):
            draw.text((77, y + 25), label, fill=(54, 67, 83), font=F16)
            heatmap(image, (ts, arr), lo, hi, (x0, y, width, 80))
            draw_gate_labels(draw, y, 80, 160)
        draw.text((80, top + 209), "State", fill=(54, 67, 83), font=F16)
        state_bar(draw, state_ts, state, lo, hi, (x0, top + 195, width, 38))
        draw.line((x0, top + 250, x0 + width, top + 250), fill=(221, 226, 231), width=1)
    # Event markers are labels, separate from the sensor data and state.
    markers = ((stamp("11:39:12"), "Kitchen", (236, 183, 65)),
               (stamp("11:40:20"), "Hall", (103, 161, 203)),
               (stamp("11:40:36"), "Living room", (66, 167, 127)))
    for ts, label, color in markers:
        x = xcoord(ts, lo, hi, x0, width)
        draw.line((x, 180, x, 982), fill=color, width=3)
        draw.text((x + 5, 958), label, fill=color, font=F16)
    time_axis(draw, lo, hi, x0, width, 1010, 20)
    image.save(HERE / "replacement-journey.png")


def seated():
    lo, hi = stamp("11:40:30"), stamp("11:58:20")
    image = Image.new("RGB", (1920, 1020), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    draw.text((82, 35), "Living room: entry and seated occupancy", fill=(25, 40, 57), font=F34)
    draw.text((85, 85), "User entered at 11:40:36 and stayed · replacement sensor · recorded integration state", fill=(72, 83, 97), font=F20)
    x0, width = 180, 1660
    ts, move, still, state_ts, state = data["Living room"]
    for label, arr, y in (("Motion", move, 155), ("Still", still, 465)):
        draw.text((65, y + 110), label, fill=(54, 67, 83), font=F25)
        heatmap(image, (ts, arr), lo, hi, (x0, y, width, 270), mode="max" if label == "Motion" else "median")
        draw_gate_labels(draw, y, 270, 160)
    draw.text((57, 839), "Occupancy", fill=(54, 67, 83), font=F20)
    state_bar(draw, state_ts, state, lo, hi, (x0, 830, width, 74))
    for a, color in ((stamp("11:40:36"), (66, 167, 127)), (stamp("11:42:15"), (212, 72, 83)),
                     (stamp("11:52:22"), (35, 144, 112))):
        x = xcoord(a, lo, hi, x0, width)
        draw.line((x, 140, x, 904), fill=color, width=2)
    time_axis(draw, lo, hi, x0, width, 940, 120)
    draw.text((180, 983), "Motion: peak within each time pixel · Still: median within each time pixel · gates 2–8", fill=(72, 83, 97), font=F16)
    image.save(HERE / "replacement-seated.png")


def compare_failure_to_throughwall():
    cases = (
        ("Kitchen through the bathroom wall", "Bathroom", stamp("11:39:15"), stamp("11:40:15"),
         "Bathroom empty; person in kitchen"),
        ("Real living-room occupant, false clear", "Living room", stamp("11:41:45"), stamp("11:42:45"),
         "Person stayed in living room; state clears at 11:42:15"),
    )
    image = Image.new("RGB", (1920, 940), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    draw.text((74, 30), "Through-wall kitchen signal vs real living-room occupancy", fill=(25, 40, 57), font=F34)
    draw.text((76, 80), "Equal 60-second windows · same 0–100 energy colors · gates 2–8 · recorded occupancy below", fill=(72, 83, 97), font=F20)
    for col, (title, sensor_name, lo, hi, description) in enumerate(cases):
        left = 65 + col * 950
        x0, width = left + 115, 760
        ts, move, still, state_ts, state = data[sensor_name]
        draw.text((left, 145), title, fill=(29, 46, 61), font=F25)
        draw.text((left, 182), description, fill=(78, 89, 103), font=F16)
        for label, arr, y in (("Motion", move, 235), ("Still", still, 495)):
            draw.text((left, y + 88), label, fill=(54, 67, 83), font=F20)
            heatmap(image, (ts, arr), lo, hi, (x0, y, width, 210), mode="max")
            draw_gate_labels(draw, y, 210, x0 - 22)
        draw.text((left, 757), "State", fill=(54, 67, 83), font=F20)
        state_bar(draw, state_ts, state, lo, hi, (x0, 742, width, 60))
        if sensor_name == "Living room":
            x = xcoord(stamp("11:42:15"), lo, hi, x0, width)
            draw.line((x, 220, x, 803), fill=(212, 72, 83), width=2)
            draw.text((x + 5, 810), "false clear", fill=(174, 53, 69), font=F16)
        time_axis(draw, lo, hi, x0, width, 852, 10)
    draw.text((76, 908), "Bright = stronger raw energy. Red state = detector vacant; green = detector occupied.",
              fill=(72, 83, 97), font=F16)
    image.save(HERE / "replacement-occupancy-vs-throughwall.png")


def compare_three_cases():
    loop_db = HERE.parents[3] / "tests/fixtures/recordings/labeled-loop-0915.db"
    with sqlite3.connect(f"file:{loop_db}?mode=ro", uri=True) as con:
        frames = con.execute("SELECT ts,move,still FROM frames WHERE sensor_id=? ORDER BY ts",
                             (SENSORS["Bathroom"][0],)).fetchall()
        states = con.execute("SELECT ts,state FROM states WHERE entity_id=? ORDER BY ts",
                             (SENSORS["Bathroom"][1],)).fetchall()
    true_bath = (
        np.array([r[0] for r in frames]),
        np.array([list(r[1]) for r in frames], dtype=np.uint8),
        np.array([list(r[2]) for r in frames], dtype=np.uint8),
        np.array([r[0] for r in states]),
        np.array([r[1] == "on" for r in states], dtype=bool),
    )
    def earlier(hms):
        return datetime.fromisoformat("2026-09-15 " + hms).replace(tzinfo=TZ).timestamp()
    cases = (
        ("Kitchen through wall", data["Bathroom"], stamp("11:39:15"), stamp("11:40:15"),
         "Sep 16 · bathroom sensor · bathroom empty"),
        ("Bathroom truly occupied", true_bath, earlier("19:24:25"), earlier("19:25:25"),
         "Sep 15 · bathroom sensor · person inside"),
        ("Living-room false clear", data["Living room"], stamp("11:41:45"), stamp("11:42:45"),
         "Sep 16 · living-room sensor · person inside"),
    )
    image = Image.new("RGB", (2180, 950), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    draw.text((72, 30), "Three sensor views: through wall, true bathroom, seated living room", fill=(25, 40, 57), font=F34)
    draw.text((74, 82), "Equal one-minute windows · same raw-energy scale 0–100 · gates 2–8 · recorded state", fill=(72, 83, 97), font=F20)
    for col, (title, values, lo, hi, description) in enumerate(cases):
        left = 60 + col * 705
        x0, width = left + 90, 555
        ts, move, still, state_ts, state = values
        draw.text((left, 145), title, fill=(29, 46, 61), font=F25)
        draw.text((left, 184), description, fill=(78, 89, 103), font=F16)
        for label, arr, y in (("Motion", move, 235), ("Still", still, 495)):
            draw.text((left, y + 88), label, fill=(54, 67, 83), font=F20)
            heatmap(image, (ts, arr), lo, hi, (x0, y, width, 210), mode="max")
            draw_gate_labels(draw, y, 210, x0 - 22)
        draw.text((left, 757), "State", fill=(54, 67, 83), font=F20)
        state_bar(draw, state_ts, state, lo, hi, (x0, 742, width, 60))
        if col == 2:
            x = xcoord(stamp("11:42:15"), lo, hi, x0, width)
            draw.line((x, 220, x, 803), fill=(212, 72, 83), width=2)
            draw.text((x + 5, 810), "false clear", fill=(174, 53, 69), font=F16)
        time_axis(draw, lo, hi, x0, width, 852, 10)
    draw.text((74, 912), "Bright = stronger gate energy · green = reported occupied · red = reported vacant",
              fill=(72, 83, 97), font=F16)
    image.save(HERE / "throughwall-bathroom-livingroom-comparison.png")


journey()
seated()
compare_failure_to_throughwall()
compare_three_cases()
