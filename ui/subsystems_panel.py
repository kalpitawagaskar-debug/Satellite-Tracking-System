"""Power / thermal / RF housekeeping bars with colour thresholds and sparklines.

Thresholds below are EXAMPLE values for the demo. Replace them with your real
limits from the SomaiyaSat design before presenting them as mission limits.
"""
from collections import deque
import tkinter as tk
from ui_base import BasePanel, mono, severity_color, mix

DEFAULT_METRICS = [
    dict(key="battery_pct", label="BATTERY", unit="%", lo=0, hi=100, warn=30, crit=15, bad_when="low"),
    dict(key="bus_v", label="BUS VOLTAGE", unit=" V", lo=3.0, hi=4.3, warn=3.5, crit=3.3, bad_when="low"),
    dict(key="solar_w", label="SOLAR INPUT", unit=" W", lo=0, hi=3, warn=None, crit=None, bad_when="low"),
    dict(key="temp_c", label="OBC TEMP", unit=" °C", lo=-20, hi=80, warn=55, crit=70, bad_when="high"),
    dict(key="rssi_dbm", label="RX RSSI", unit=" dBm", lo=-140, hi=-60, warn=-120, crit=-130, bad_when="low"),
]
SEGMENTS = 24


class _Row(tk.Canvas):
    def __init__(self, master, spec, colors):
        super().__init__(master, height=40, bg=colors["panel"], highlightthickness=0)
        self.spec, self.c = spec, colors
        self.hist, self.value = deque(maxlen=60), None
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, v):
        self.value = v
        self.hist.append(v)
        self.draw()

    def clear(self):
        self.value = None
        self.hist.clear()
        self.draw()

    def draw(self):
        self.delete("all")
        s, c = self.spec, self.c
        w = self.winfo_width()
        self.create_text(2, 8, text=s["label"], fill=c["muted"], anchor="w", font=mono(8, True))
        if self.value is None:
            return
        col = severity_color(self.value, s["warn"], s["crit"], s["bad_when"], c)
        self.create_text(w - 2, 8, text=f"{self.value:.1f}{s['unit']}", fill=col, anchor="e", font=mono(10, True))
        bw = w - 90
        frac = max(0, min(1, (self.value - s["lo"]) / (s["hi"] - s["lo"])))
        seg_w = bw / SEGMENTS
        for i in range(SEGMENTS):
            on = i < round(frac * SEGMENTS)
            self.create_rectangle(2 + i * seg_w, 20, 2 + (i + 1) * seg_w - 2, 34,
                                  fill=col if on else mix(c["panel"], c["border"], 0.7), outline="")
        if len(self.hist) > 1:
            span = (s["hi"] - s["lo"]) or 1
            pts = [(w - 80 + i * 78 / 59, 36 - 14 * (max(s["lo"], min(s["hi"], h)) - s["lo"]) / span)
                   for i, h in enumerate(self.hist)]
            self.create_line(*[a for p in pts for a in p], fill=col)


class SubsystemsPanel(BasePanel):
    def __init__(self, master, colors=None, metrics=None, **kw):
        super().__init__(master, "Subsystems", "EPS · THERMAL · RF", colors, **kw)
        self.rows = {}
        for spec in (metrics or DEFAULT_METRICS):
            r = _Row(self.body, spec, self.c)
            r.pack(fill="x", pady=2)
            self.rows[spec["key"]] = r

    def update_values(self, data):
        for k, v in data.items():
            if k in self.rows:
                self.rows[k].set(v)

    def clear_values(self):
        for row in self.rows.values():
            row.clear()
