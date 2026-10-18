"""SDR-style spectrum plot + scrolling waterfall. Feed it rows of 0..1 intensities.

start_demo() uses a SIMULATED signal source so the panel looks alive before you
have a real SDR/decoder feed. The panel badge says SIMULATED while it runs.
"""
import math
import random
import tkinter as tk
from ui_base import BasePanel, mono, mix

ANCHORS = [(0.00, "#050816"), (0.25, "#1e1b6b"), (0.50, "#7c1d8f"), (0.75, "#f97316"), (1.00, "#fde68a")]


def _lut(n=256):
    out = []
    for i in range(n):
        t = i / (n - 1)
        for (t0, c0), (t1, c1) in zip(ANCHORS, ANCHORS[1:]):
            if t0 <= t <= t1:
                out.append(mix(c0, c1, (t - t0) / (t1 - t0)))
                break
    return out


LUT = _lut()


class WaterfallPanel(BasePanel):
    BINS, ROWS = 128, 56

    def __init__(self, master, colors=None, center_mhz=437.0, span_khz=48, markers=None, **kw):
        super().__init__(master, "RF waterfall", "", colors, **kw)
        self.center, self.span = center_mhz, span_khz
        self.markers = markers or []          # [(fraction 0..1, "M17"), ...]
        self.rows = [[0.0] * self.BINS for _ in range(self.ROWS)]
        self.peak = [0.0] * self.BINS
        self.t = 0
        self.spec = tk.Canvas(self.body, bg=self.c["panel2"], height=90, highlightthickness=0)
        self.spec.pack(fill="x")
        self.wf = tk.Canvas(self.body, bg="#050816", height=170, highlightthickness=0)
        self.wf.pack(fill="both", expand=True, pady=(4, 0))
        self.img = tk.PhotoImage(width=self.BINS, height=self.ROWS)
        self._zoomed = None
        self.wf.bind("<Configure>", lambda e: self._render())

    def _layout(self):
        w = max(self.wf.winfo_width(), self.BINS)
        zx = max(1, w // self.BINS)
        return zx, (w - zx * self.BINS) // 2

    def push_row(self, values):
        self.rows.append(list(values))
        self.rows.pop(0)
        self.peak = [max(p * 0.97, v) for p, v in zip(self.peak, values)]
        self._render()

    def _render(self):
        zx, x0 = self._layout()
        zy = max(1, self.wf.winfo_height() // self.ROWS)
        data = " ".join("{" + " ".join(LUT[min(255, int(v * 255))] for v in r) + "}" for r in self.rows)
        self.img.put(data, to=(0, 0))
        self._zoomed = self.img.zoom(zx, zy)
        self.wf.delete("all")
        self.wf.create_image(x0, 0, image=self._zoomed, anchor="nw")
        self._draw_spec(zx, x0)

    def _draw_spec(self, zx, x0):
        cv, c = self.spec, self.c
        cv.delete("all")
        h = max(cv.winfo_height(), 60)
        W = zx * self.BINS
        for g in (0.25, 0.5, 0.75):
            cv.create_line(x0, h * g, x0 + W, h * g, fill=c["grid"])
        last = self.rows[-1]
        pts = [(x0 + i * zx, h - 14 - v * (h - 28)) for i, v in enumerate(last)]
        cv.create_polygon(x0, h - 14, *[a for p in pts for a in p], x0 + W, h - 14,
                          fill=mix(c["panel2"], c["accent"], 0.35), outline="")
        cv.create_line(*[a for p in pts for a in p], fill=c["accent"])
        cv.create_line(*[a for i, v in enumerate(self.peak)
                         for a in (x0 + i * zx, h - 14 - v * (h - 28))], fill=c["warn"])
        for frac, label in self.markers:
            x = x0 + frac * W
            cv.create_line(x, 6, x, h - 14, fill=c["violet"], dash=(2, 3))
            cv.create_text(x + 3, 8, text=label, fill=c["violet"], anchor="w", font=mono(8, True))
        lo = self.center - self.span / 2000
        hi = self.center + self.span / 2000
        cv.create_text(x0, h - 3, text=f"{lo:.4f}", fill=c["muted"], anchor="sw", font=mono(7))
        cv.create_text(x0 + W / 2, h - 3, text=f"{self.center:.4f} MHz", fill=c["text"], anchor="s", font=mono(7))
        cv.create_text(x0 + W, h - 3, text=f"{hi:.4f}", fill=c["muted"], anchor="se", font=mono(7))

    # ---- simulated source
    def start_demo(self, ms=120):
        self.badge.config(text="SIMULATED", fg=self.c["warn"])
        self.every(ms, self._demo_step)

    def _demo_step(self):
        self.t += 1
        sigs = [(0.5 + 0.06 * math.sin(self.t / 25), 3.0, 0.95), (0.22, 2.0, 0.7 if (self.t // 40) % 2 else 0.0)]
        row = []
        for i in range(self.BINS):
            f = i / self.BINS
            v = 0.07 + 0.06 * random.random()
            for cf, wd, amp in sigs:
                v += amp * math.exp(-((f - cf) * self.BINS / wd) ** 2)
            row.append(min(1.0, v))
        self.push_row(row)
