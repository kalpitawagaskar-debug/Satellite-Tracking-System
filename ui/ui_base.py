"""Shared palette, font helpers and BasePanel card used by the extra panels.

Each panel accepts colors={...} so you can pass your own theme.py palette.
Any key you leave out falls back to the defaults below, so nothing breaks
if your theme uses different key names.
"""
import tkinter as tk

PALETTE = {
    "bg": "#0a0e17", "panel": "#111827", "panel2": "#0d1420",
    "border": "#1e2a40", "grid": "#1b2638",
    "text": "#dbe4f3", "muted": "#6f7f9a",
    "accent": "#38bdf8", "good": "#22c55e", "warn": "#f59e0b",
    "crit": "#ef4444", "violet": "#a78bfa",
}


def mono(size=9, bold=False):
    return ("Consolas", size, "bold" if bold else "normal")


def sans(size=10, bold=False):
    return ("Segoe UI", size, "bold" if bold else "normal")


def mix(c1, c2, t):
    """Blend two #rrggbb colours; t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def severity_color(value, warn, crit, bad_when, c):
    """Return good/warn/crit colour. warn/crit may be None (always good)."""
    if warn is None or crit is None:
        return c["accent"]
    if bad_when == "low":
        return c["crit"] if value <= crit else c["warn"] if value <= warn else c["good"]
    return c["crit"] if value >= crit else c["warn"] if value >= warn else c["good"]


class BasePanel(tk.Frame):
    """Dark card with an accent bar, title and a right-aligned badge label."""

    def __init__(self, master, title="", badge="", colors=None, **kw):
        self.c = {**PALETTE, **(colors or {})}
        super().__init__(master, bg=self.c["panel"], highlightthickness=1,
                         highlightbackground=self.c["border"], **kw)
        head = tk.Frame(self, bg=self.c["panel"])
        head.pack(fill="x", padx=10, pady=(8, 4))
        tk.Frame(head, bg=self.c["accent"], width=3, height=14).pack(side="left", padx=(0, 8))
        self.title_label = tk.Label(head, text=title.upper(), bg=self.c["panel"], fg=self.c["text"],
                                    font=sans(9, True))
        self.title_label.pack(side="left")
        self.badge = tk.Label(head, text=badge, bg=self.c["panel"], fg=self.c["muted"],
                              font=mono(8))
        self.badge.pack(side="right")
        self.body = tk.Frame(self, bg=self.c["panel"])
        self.body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._jobs = {}
        self.bind("<Destroy>", self._cancel_jobs, add="+")

    def set_title(self, title):
        self.title_label.config(text=title.upper())

    def every(self, ms, fn):
        """Run fn every ms milliseconds until the panel is destroyed."""
        def run():
            if not self.winfo_exists():
                return
            try:
                fn()
            finally:
                if self.winfo_exists():
                    self._jobs[fn] = self.after(ms, run)
        self._jobs[fn] = self.after(ms, run)

    def _cancel_jobs(self, event):
        if event.widget is self:
            for job in self._jobs.values():
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
