"""Borderless boot splash: twinkling stars, orbiting dot, staged loading text.

    root.withdraw()
    SplashScreen(root, steps=["Opening SQLite...", "Loading TLEs..."], on_done=root.deiconify)
"""
import math
import random
import tkinter as tk
from ui_base import PALETTE, mono


class SplashScreen(tk.Toplevel):
    W, H = 640, 360

    def __init__(self, root, title="SATELLITE TRACKING SYSTEM", subtitle="GROUND STATION CONTROL",
                 steps=None, on_done=None, step_ms=450, colors=None):
        super().__init__(root)
        self.c = {**PALETTE, **(colors or {})}
        self.steps = steps or ["Initialising UI", "Opening SQLite database", "Loading orbital elements",
                               "Starting telemetry decoder", "Ready"]
        self.on_done, self.step_ms, self.i, self.t = on_done, step_ms, 0, 0
        self.overrideredirect(True)
        x = (self.winfo_screenwidth() - self.W) // 2
        y = (self.winfo_screenheight() - self.H) // 2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.cv = tk.Canvas(self, width=self.W, height=self.H, bg="#03050b", highlightthickness=1,
                            highlightbackground=self.c["border"])
        self.cv.pack()
        self.stars = [(random.randint(0, self.W), random.randint(0, self.H),
                       random.random() * 6.28, random.uniform(0.5, 1.5)) for _ in range(90)]
        self.title_txt, self.sub_txt = title, subtitle
        self._animate()
        self.after(self.step_ms, self._next)

    def _animate(self):
        if not self.winfo_exists():
            return
        cv, c = self.cv, self.c
        cv.delete("all")
        self.t += 1
        for x, y, ph, sz in self.stars:
            b = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.t * 0.08 + ph))
            g = int(60 + 190 * b)
            cv.create_oval(x, y, x + sz, y + sz, fill=f"#{g:02x}{g:02x}{min(255, g + 20):02x}", outline="")
        cx, cy = self.W / 2, 140
        cv.create_oval(cx - 90, cy - 40, cx + 90, cy + 40, outline=c["border"])
        a = self.t * 0.07
        cv.create_oval(cx + 90 * math.cos(a) - 5, cy + 40 * math.sin(a) - 5,
                       cx + 90 * math.cos(a) + 5, cy + 40 * math.sin(a) + 5, fill=c["good"], outline="")
        cv.create_oval(cx - 18, cy - 18, cx + 18, cy + 18, fill="#1c4f9c", outline=c["accent"])
        cv.create_text(cx, 225, text=self.title_txt, fill=c["text"], font=("Segoe UI", 26, "bold"))
        cv.create_text(cx, 252, text=self.sub_txt, fill=c["accent"], font=mono(10, True))
        frac = min(1, self.i / max(1, len(self.steps)))
        cv.create_rectangle(120, 300, self.W - 120, 306, outline=c["border"])
        cv.create_rectangle(120, 300, 120 + (self.W - 240) * frac, 306, fill=c["accent"], outline="")
        label = self.steps[min(self.i, len(self.steps) - 1)]
        cv.create_text(cx, 326, text=label, fill=c["muted"], font=mono(9))
        self.after(40, self._animate)

    def _next(self):
        self.i += 1
        if self.i >= len(self.steps):
            self.after(300, self._close)
        else:
            self.after(self.step_ms, self._next)

    def _close(self):
        self.destroy()
        if self.on_done:
            self.on_done()
