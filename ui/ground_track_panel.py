"""World map with ground track, coverage footprint, day/night shading and a
pulsing satellite marker. Continents are a stylised outline, not survey data.
"""
import math
import datetime as dt
from collections import deque
import tkinter as tk
from ui_base import BasePanel, mono, mix

RE_KM = 6371.0
CONTINENTS = {
    "na": [(-168, 66), (-140, 70), (-95, 72), (-80, 68), (-62, 60), (-55, 50), (-70, 43),
           (-76, 35), (-81, 25), (-97, 26), (-105, 22), (-117, 32), (-124, 40), (-125, 49), (-140, 60)],
    "sa": [(-80, 9), (-62, 11), (-50, 0), (-35, -6), (-40, -22), (-58, -38), (-66, -55),
           (-75, -50), (-72, -30), (-81, -5)],
    "eu": [(-10, 36), (-9, 43), (0, 50), (10, 55), (30, 70), (70, 73), (110, 77), (150, 70),
           (180, 66), (170, 60), (140, 52), (130, 35), (122, 30), (120, 22), (108, 10), (100, 2),
           (98, 15), (88, 22), (80, 10), (73, 18), (67, 25), (57, 25), (52, 13), (35, 28), (30, 36), (10, 38)],
    "af": [(-17, 21), (-6, 36), (10, 37), (32, 31), (43, 12), (51, 11), (40, -15), (33, -27),
           (20, -35), (12, -18), (9, 4), (-8, 5), (-17, 14)],
    "au": [(114, -22), (130, -12), (142, -11), (153, -26), (146, -39), (130, -32), (115, -34)],
    "gl": [(-55, 60), (-20, 70), (-20, 83), (-60, 82), (-72, 77)],
    "an": [(-180, -72), (180, -72), (180, -90), (-180, -90)],
}


def propagate_circular(t_s, inc_deg=97.5, period_min=95.5, lon0=0.0):
    """Very simple circular-orbit model for demos (not SGP4). Returns lat, lon."""
    u = 2 * math.pi * t_s / (period_min * 60)
    i = math.radians(inc_deg)
    lat = math.degrees(math.asin(math.sin(i) * math.sin(u)))
    lon = math.degrees(math.atan2(math.cos(i) * math.sin(u), math.cos(u)))
    lon = lon - 360.0 * t_s / 86164.1 + lon0
    return lat, (lon + 180) % 360 - 180


def footprint(lat, lon, alt_km, n=72):
    """Points (lat, lon) on the edge of the horizon circle seen from the satellite."""
    ang = math.acos(RE_KM / (RE_KM + alt_km))
    la, lo = math.radians(lat), math.radians(lon)
    pts = []
    for k in range(n + 1):
        b = 2 * math.pi * k / n
        la2 = math.asin(math.sin(la) * math.cos(ang) + math.cos(la) * math.sin(ang) * math.cos(b))
        lo2 = lo + math.atan2(math.sin(b) * math.sin(ang) * math.cos(la),
                              math.cos(ang) - math.sin(la) * math.sin(la2))
        pts.append((math.degrees(la2), (math.degrees(lo2) + 180) % 360 - 180))
    return pts


class GroundTrackPanel(BasePanel):
    def __init__(self, master, colors=None, station=("MUMBAI GS", 19.08, 72.90),
                 altitude_km=550, **kw):
        super().__init__(master, "Ground track", "", colors, **kw)
        self.station, self.alt = station, altitude_km
        self.trail = deque(maxlen=200)
        self.pos = None
        self.satellite_name = "SOMAIYASAT"
        self.phase = 0.0
        self.cv = tk.Canvas(self.body, bg=self.c["panel2"], highlightthickness=0, width=640, height=320)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda e: self._draw_static())
        self.every(80, self._pulse)
        self.every(30000, self._draw_night)

    # ---- geometry
    def _xy(self, lat, lon):
        return (lon + 180) / 360 * self.cv.winfo_width(), (90 - lat) / 180 * self.cv.winfo_height()

    def _flat(self, pts):
        return [v for la, lo in pts for v in self._xy(la, lo)]

    # ---- static layers
    def _draw_static(self):
        cv, c = self.cv, self.c
        cv.delete("static")
        for lon in range(-180, 181, 30):
            x, _ = self._xy(0, lon)
            cv.create_line(x, 0, x, cv.winfo_height(), fill=c["grid"], tags="static")
        for lat in range(-90, 91, 30):
            _, y = self._xy(lat, 0)
            cv.create_line(0, y, cv.winfo_width(), y, fill=c["grid"], tags="static")
        for poly in CONTINENTS.values():
            cv.create_polygon(self._flat([(la, lo) for lo, la in poly]), fill="#17263f",
                              outline="#2d4468", tags="static")
        name, la, lo = self.station
        x, y = self._xy(la, lo)
        cv.create_polygon(x, y - 6, x + 5, y, x, y + 6, x - 5, y, fill=c["warn"], outline="", tags="static")
        cv.create_text(x + 9, y - 8, text=name, fill=c["warn"], anchor="w", font=mono(8, True), tags="static")
        cv.create_text(6, cv.winfo_height() - 6, text="STYLISED MAP", fill=c["muted"],
                       anchor="sw", font=mono(7), tags="static")
        cv.tag_lower("static")
        self._draw_night()
        self._draw_dynamic()

    def _draw_night(self):
        cv = self.cv
        cv.delete("night")
        now = dt.datetime.now(dt.timezone.utc)
        doy = now.timetuple().tm_yday
        dec = math.radians(23.44 * math.sin(2 * math.pi * (doy - 81) / 365))
        if abs(dec) < 0.01:
            dec = 0.01
        lon_s = -((now.hour + now.minute / 60) - 12) * 15
        pts = [(math.degrees(math.atan(-math.cos(math.radians(lo - lon_s)) / math.tan(dec))), lo)
               for lo in range(-180, 181, 4)]
        edge = -90 if dec > 0 else 90
        pts += [(edge, 180), (edge, -180)]
        cv.create_polygon(self._flat(pts), fill="#02050d", stipple="gray50", outline="", tags="night")
        cv.tag_raise("night", "static")

    # ---- dynamic layers
    def update_position(self, lat, lon, alt_km=None):
        self.alt = alt_km or self.alt
        self.pos = (lat, lon)
        self.trail.append((lat, lon))
        self.badge.config(text=f"LAT {lat:+06.2f}  LON {lon:+07.2f}  ALT {self.alt:.0f} km")
        self._draw_dynamic()

    def set_satellite_name(self, name):
        self.satellite_name = name
        self._draw_dynamic()

    def clear_position(self, message="ORBIT POSITION UNAVAILABLE"):
        self.pos = None
        self.trail.clear()
        self.badge.config(text=message)
        self._draw_dynamic()

    def _draw_dynamic(self):
        cv, c = self.cv, self.c
        cv.delete("dyn")
        cv.delete("marker")
        if not self.pos:
            return
        seg, prev = [], None
        pts = list(self.trail)
        for i, p in enumerate(pts):
            if prev and abs(p[1] - prev[1]) > 180:
                seg = []
            seg.append(p)
            if len(seg) >= 2:
                cv.create_line(*self._flat(seg[-2:]), fill=mix(c["panel2"], c["accent"], i / len(pts)),
                               width=2, tags="dyn")
            prev = p
        fp = footprint(*self.pos, self.alt)
        if max(abs(a[1] - b[1]) for a, b in zip(fp, fp[1:])) < 180:
            cv.create_polygon(self._flat(fp), fill=c["accent"], stipple="gray12",
                              outline=c["accent"], tags="dyn")
        self._draw_marker()

    def _draw_marker(self):
        if not self.pos:
            return
        cv, c = self.cv, self.c
        cv.delete("marker")
        x, y = self._xy(*self.pos)
        r = 7 + 5 * (0.5 + 0.5 * math.sin(self.phase))
        cv.create_oval(x - r, y - r, x + r, y + r, outline=c["good"], width=1, tags="marker")
        cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=c["good"], outline="white", tags="marker")
        cv.create_text(x + 10, y + 10, text=self.satellite_name, fill=c["text"], anchor="w",
                       font=mono(8, True), tags="marker")

    def _pulse(self):
        self.phase += 0.35
        self._draw_marker()
