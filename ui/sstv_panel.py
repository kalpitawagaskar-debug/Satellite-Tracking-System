"""SSTV receive viewer: image appears line by line with a scan cursor, then is
added to a thumbnail strip. make_test_pattern() generates a demo 'Earth limb'
image so the panel works without a real decoder. Use set_source(PhotoImage)
to feed real decoded images (320x240).
"""
import math
import random
import tkinter as tk
from ui_base import BasePanel, mono, mix

W, H = 320, 240


def make_test_pattern():
    rnd = random.Random(7)
    img = tk.PhotoImage(width=W, height=H)
    cx, cy, R = W / 2, H + 170, 250
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            d = math.hypot(x - cx, y - cy)
            if d < R:
                n = math.sin(x * 0.045) + math.sin(y * 0.09 + x * 0.03) + math.sin(x * 0.11 - y * 0.05)
                base = "#8a7a4a" if n > 1.15 else "#1c4f9c"
                row.append(mix(base, "#9fd4ff", max(0, 1 - (R - d) / 28) * 0.8))
            elif d < R + 14:
                row.append(mix("#38bdf8", "#02030a", (d - R) / 14))
            else:
                row.append("#ffffff" if rnd.random() < 0.003 else "#02030a")
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    return img


class SSTVPanel(BasePanel):
    def __init__(self, master, colors=None, **kw):
        super().__init__(master, "SSTV receiver", "IDLE", colors, **kw)
        c = self.c
        self.src = make_test_pattern()
        self.dst = tk.PhotoImage(width=W, height=H)
        self.line, self.job, self.thumbs = 0, None, []
        self.cv = tk.Canvas(self.body, bg="#000", width=W, height=H, highlightthickness=1,
                            highlightbackground=c["border"])
        self.cv.pack(pady=(0, 6))
        self.cv.create_image(0, 0, image=self.dst, anchor="nw")
        self.cv.create_text(W / 2, H / 2, text="NO SIGNAL\nData > Simulate SSTV image", fill=c["muted"],
                            font=mono(9), justify="center", tags="idle")
        self.bar = tk.Canvas(self.body, height=8, bg=c["panel2"], highlightthickness=0)
        self.bar.pack(fill="x")
        self.info = tk.Label(self.body, text="LINE 0/240   SNR --", bg=c["panel"], fg=c["muted"],
                             font=mono(8), anchor="w")
        self.info.pack(fill="x", pady=(4, 4))
        self.strip = tk.Frame(self.body, bg=c["panel"])
        self.strip.pack(fill="x")

    def set_source(self, photo):
        self.src = photo

    def start_reception(self, lines_per_tick=2, ms=40):
        if self.job:
            return
        self.line = 0
        self.dst.blank()
        self.cv.delete("idle")
        self.badge.config(text="● RECEIVING", fg=self.c["crit"])
        self._step(lines_per_tick, ms)

    def _step(self, n, ms):
        for _ in range(n):
            if self.line >= H:
                return self._finish()
            self.dst.tk.call(str(self.dst), "copy", str(self.src), "-from", 0, self.line, W,
                             self.line + 1, "-to", 0, self.line)
            self.line += 1
        self.cv.delete("scan")
        self.cv.create_line(0, self.line, W, self.line, fill=self.c["good"], tags="scan")
        self.bar.delete("all")
        self.bar.create_rectangle(0, 0, self.bar.winfo_width() * self.line / H, 8,
                                  fill=self.c["accent"], outline="")
        self.info.config(text=f"LINE {self.line}/{H}   SNR {8 + 3 * math.sin(self.line / 15):.1f} dB (sim)")
        self.job = self.after(ms, self._step, n, ms)

    def _finish(self):
        self.job = None
        self.cv.delete("scan")
        self.badge.config(text="COMPLETE", fg=self.c["good"])
        thumb = self.dst.copy().subsample(4, 4)
        self.thumbs = (self.thumbs + [thumb])[-4:]
        for w in self.strip.winfo_children():
            w.destroy()
        for t in self.thumbs:
            tk.Label(self.strip, image=t, bg=self.c["panel"], bd=1, relief="solid").pack(side="left", padx=2)
