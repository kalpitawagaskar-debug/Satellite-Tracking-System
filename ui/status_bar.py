"""Bottom status bar: DB link LED, frame counter, last-RX age, scrolling ticker, UTC clock."""
import datetime as dt
import tkinter as tk
from ui_base import PALETTE, mono


class StatusBar(tk.Frame):
    def __init__(self, master, colors=None, **kw):
        self.c = {**PALETTE, **(colors or {})}
        c = self.c
        super().__init__(master, bg=c["panel2"], height=26, highlightthickness=1,
                         highlightbackground=c["border"], **kw)
        self.pack_propagate(False)
        self.led = tk.Canvas(self, width=14, height=14, bg=c["panel2"], highlightthickness=0)
        self.led.pack(side="left", padx=(8, 2))
        self.db_lbl = tk.Label(self, text="SQLITE", bg=c["panel2"], fg=c["muted"], font=mono(8, True))
        self.db_lbl.pack(side="left", padx=(0, 12))
        self.frames_lbl = tk.Label(self, text="FRAMES 0", bg=c["panel2"], fg=c["text"], font=mono(8))
        self.frames_lbl.pack(side="left", padx=6)
        self.rx_lbl = tk.Label(self, text="LAST RX --", bg=c["panel2"], fg=c["text"], font=mono(8))
        self.rx_lbl.pack(side="left", padx=6)
        self.clock = tk.Label(self, text="", bg=c["panel2"], fg=c["accent"], font=mono(9, True))
        self.clock.pack(side="right", padx=10)
        self.ticker = tk.Canvas(self, bg=c["panel2"], highlightthickness=0, height=22)
        self.ticker.pack(side="left", fill="both", expand=True, padx=8)
        self._text, self._x, self._last_rx, self._ok = "", 0, None, False
        self.set_db(False)
        self.after(40, self._scroll)
        self.after(500, self._tick)

    def set_db(self, ok):
        self._ok = ok
        col = self.c["good"] if ok else self.c["crit"]
        self.led.delete("all")
        self.led.create_oval(2, 2, 12, 12, fill=col, outline="")
        self.db_lbl.config(text="SQLITE OK" if ok else "SQLITE OFFLINE", fg=col)

    def set_frames(self, count, last_rx=None):
        self.frames_lbl.config(text=f"FRAMES {count:,}")
        self._last_rx = last_rx
        if not last_rx:
            self.rx_lbl.config(text="LAST RX --")

    def set_ticker(self, text):
        self._text, self._x = text, self.ticker.winfo_width()

    def _scroll(self):
        if not self.winfo_exists():
            return
        self.ticker.delete("all")
        item = self.ticker.create_text(self._x, 11, text=self._text, fill=self.c["muted"],
                                       anchor="w", font=mono(9))
        x0, _, x1, _ = self.ticker.bbox(item) or (0, 0, 0, 0)
        self._x = self.ticker.winfo_width() if x1 < 0 else self._x - 2
        self.after(40, self._scroll)

    def _tick(self):
        if not self.winfo_exists():
            return
        now = dt.datetime.now(dt.timezone.utc)
        self.clock.config(text=now.strftime("%Y-%m-%d %H:%M:%S UTC"))
        if self._last_rx:
            s = int((now - self._last_rx).total_seconds())
            age = f"{s // 60:02d}:{s % 60:02d}" if s < 3600 else f"{s // 3600}h {s % 3600 // 60:02d}m"
            self.rx_lbl.config(text=f"LAST RX {age} ago")
        self.after(500, self._tick)
