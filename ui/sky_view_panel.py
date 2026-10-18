"""Polar azimuth/elevation plot of the current or next pass over the ground station."""
import math
import tkinter as tk
from ui_base import BasePanel, mono


def make_demo_pass(max_el=62, az_in=200, az_out=40, n=60):
    """Fake pass arc [(az, el), ...] for testing. Replace with Skyfield output."""
    pts = []
    for k in range(n + 1):
        f = k / n
        el = max_el * math.sin(math.pi * f) ** 0.8
        az = (az_in + (((az_out - az_in + 540) % 360) - 180) * f) % 360
        pts.append((az, el))
    return pts


class SkyViewPanel(BasePanel):
    def __init__(self, master, colors=None, **kw):
        super().__init__(master, "Sky view", "AZ --  EL --", colors, **kw)
        self.cv = tk.Canvas(self.body, bg=self.c["panel2"], highlightthickness=0, width=300, height=300)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda e: self._draw())
        self.arc, self.cur, self.phase = [], None, 0.0
        self.every(80, self._pulse)

    def set_satellite_name(self, name):
        self.set_title("Sky view · " + name.split(" (")[0])

    def _geom(self):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        return w / 2, h / 2, max(10, min(w, h) / 2 - 22)

    def _pt(self, az, el):
        cx, cy, R = self._geom()
        r = R * (90 - el) / 90
        a = math.radians(az)
        return cx + r * math.sin(a), cy - r * math.cos(a)

    def set_pass(self, points):
        self.arc = list(points)
        self._draw()

    def set_position(self, az, el):
        self.cur = (az, el)
        self.badge.config(text=f"AZ {az:5.1f}  EL {el:4.1f}")

    def _draw(self):
        cv, c = self.cv, self.c
        cv.delete("all")
        cx, cy, R = self._geom()
        for el in (0, 30, 60):
            r = R * (90 - el) / 90
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=c["grid"] if el else c["border"], width=1)
            if el:
                cv.create_text(cx + 3, cy - r + 8, text=f"{el}°", fill=c["muted"], font=mono(7), anchor="w")
        cv.create_line(cx - R, cy, cx + R, cy, fill=c["grid"])
        cv.create_line(cx, cy - R, cx, cy + R, fill=c["grid"])
        for t, a in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            x = cx + (R + 12) * math.sin(math.radians(a))
            y = cy - (R + 12) * math.cos(math.radians(a))
            cv.create_text(x, y, text=t, fill=c["accent"] if t == "N" else c["muted"], font=mono(9, True))
        if len(self.arc) > 1:
            flat = [v for az, el in self.arc for v in self._pt(az, el)]
            cv.create_line(*flat, fill=c["accent"], width=2, smooth=True)
            for tag, p in (("AOS", self.arc[0]), ("LOS", self.arc[-1])):
                x, y = self._pt(*p)
                cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=c["warn"], outline="")
                cv.create_text(x + 6, y, text=tag, fill=c["warn"], anchor="w", font=mono(7, True))
        self._draw_marker()

    def _draw_marker(self):
        self.cv.delete("marker")
        if not self.cur:
            return
        x, y = self._pt(*self.cur)
        r = 6 + 4 * (0.5 + 0.5 * math.sin(self.phase))
        self.cv.create_oval(x - r, y - r, x + r, y + r, outline=self.c["good"], tags="marker")
        self.cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=self.c["good"], outline="white", tags="marker")

    def _pulse(self):
        self.phase += 0.35
        self._draw_marker()
