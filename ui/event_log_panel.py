"""Terminal-style mission event log with severity colours and filter chips."""
import datetime as dt
from collections import deque
import tkinter as tk
from ui_base import BasePanel, mono

LEVELS = {"INFO": 0, "OK": 0, "RX": 0, "WARN": 1, "CRIT": 2}
FILTERS = (("ALL", 0), ("WARN+", 1), ("CRIT", 2))


class EventLogPanel(BasePanel):
    def __init__(self, master, colors=None, max_entries=400, **kw):
        super().__init__(master, "Event log", "", colors, **kw)
        c = self.c
        self.entries, self.min_level = deque(maxlen=max_entries), 0
        bar = tk.Frame(self.body, bg=c["panel"])
        bar.pack(fill="x", pady=(0, 4))
        self.chips = {}
        for name, lvl in FILTERS:
            lb = tk.Label(bar, text=name, font=mono(8, True), padx=8, pady=2, cursor="hand2")
            lb.pack(side="left", padx=(0, 4))
            lb.bind("<Button-1>", lambda e, l=lvl: self._set_filter(l))
            self.chips[lvl] = lb
        self.text = tk.Text(self.body, bg=c["panel2"], fg=c["text"], font=mono(9), height=10,
                            bd=0, highlightthickness=0, wrap="word", state="disabled", padx=8, pady=6)
        self.text.pack(fill="both", expand=True)
        colors_by_level = {"INFO": c["muted"], "OK": c["good"], "RX": c["violet"],
                           "WARN": c["warn"], "CRIT": c["crit"]}
        for lvl, col in colors_by_level.items():
            self.text.tag_config(lvl, foreground=col)
        self.text.tag_config("ts", foreground=c["muted"])
        self._set_filter(0)

    def log(self, level, message):
        level = level.upper() if level.upper() in LEVELS else "INFO"
        ts = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
        self.entries.append((ts, level, message))
        if LEVELS[level] >= self.min_level:
            self._write(ts, level, message)
            self.text.see("end")

    def _write(self, ts, level, message):
        self.text.config(state="normal")
        self.text.insert("end", f"{ts} ", "ts")
        self.text.insert("end", f"{level:<4} {message}\n", level)
        self.text.config(state="disabled")

    def _set_filter(self, lvl):
        self.min_level = lvl
        for l, lb in self.chips.items():
            active = l == lvl
            lb.config(bg=self.c["accent"] if active else self.c["panel2"],
                      fg="#06101c" if active else self.c["muted"])
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        for ts, level, msg in self.entries:
            if LEVELS[level] >= lvl:
                self._write(ts, level, msg)
        self.text.see("end")
