"""Upcoming-pass table with a live countdown to AOS (acquisition of signal)."""
import datetime as dt
import tkinter as tk
from tkinter import ttk
from ui_base import BasePanel, mono, sans

COLS = (("sat", "SATELLITE", 104), ("aos", "AOS UTC", 104), ("los", "LOS UTC", 104),
        ("dur", "DUR", 58), ("el", "MAX EL", 60), ("q", "QUALITY", 80))


def _clock(t, now):
    """HH:MM:SS, plus +1d / +2d when the time is not today (UTC)."""
    days = (t.date() - now.date()).days
    return t.strftime("%H:%M:%S") + (f" +{days}d" if days > 0 else "")


def _quality(el):
    return "EXCELLENT" if el >= 40 else "GOOD" if el >= 20 else "LOW"


class PassTablePanel(BasePanel):
    """set_passes([{'name','aos','los','max_el'}...]) with timezone-aware UTC datetimes."""

    def __init__(self, master, colors=None, **kw):
        super().__init__(master, "Pass schedule", "UTC", colors, **kw)
        c = self.c
        self.passes = []
        self.next_lbl = tk.Label(self.body, text="NEXT PASS  --", bg=c["panel2"], fg=c["accent"],
                                 font=mono(13, True), anchor="w", padx=10, pady=6)
        self.next_lbl.pack(fill="x", pady=(0, 6))
        st = ttk.Style(self)
        if st.theme_use() != "clam":
            st.theme_use("clam")  # clam honours custom colours on every OS
        st.configure("Pass.Treeview", background=c["panel"], fieldbackground=c["panel"],
                     foreground=c["text"], rowheight=24, borderwidth=0, bordercolor=c["panel"],
                     lightcolor=c["panel"], darkcolor=c["panel"], font=mono(9))
        st.configure("Pass.Treeview.Heading", background=c["panel2"], foreground=c["muted"],
                     relief="flat", font=sans(8, True))
        st.map("Pass.Treeview", background=[("selected", c["border"])])
        self.tree = ttk.Treeview(self.body, columns=[k for k, _, _ in COLS], show="headings",
                                 style="Pass.Treeview", height=6, selectmode="browse")
        for key, label, w in COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=w, anchor="w" if key == "sat" else "center")
        self.tree.tag_configure("EXCELLENT", foreground=c["good"])
        self.tree.tag_configure("GOOD", foreground=c["accent"])
        self.tree.tag_configure("LOW", foreground=c["warn"])
        self.tree.tag_configure("LIVE", foreground="#ffffff", background="#14532d")
        self.tree.pack(fill="both", expand=True)
        self.every(500, self._tick)

    def set_passes(self, passes):
        self.passes = sorted(passes, key=lambda p: p["aos"])
        self._refresh()

    def set_satellite_name(self, name):
        self.set_title(f"Pass schedule · {name}")

    def _refresh(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.passes = [p for p in self.passes if p["los"] > now]
        self.tree.delete(*self.tree.get_children())
        for p in self.passes:
            live = p["aos"] <= now
            q = _quality(p["max_el"])
            dur = int((p["los"] - p["aos"]).total_seconds())
            self.tree.insert("", "end", tags=("LIVE" if live else q,), values=(
                p["name"].split(" (")[0], _clock(p["aos"], now), _clock(p["los"], now),
                f"{dur // 60}m{dur % 60:02d}s", f"{p['max_el']:.0f}°", "LIVE" if live else q))

    def _tick(self):
        now = dt.datetime.now(dt.timezone.utc)
        if self.passes and self.passes[0]["los"] <= now:
            self._refresh()
        if not self.passes:
            self.next_lbl.config(text="NEXT PASS  --", fg=self.c["muted"])
            return
        p = self.passes[0]
        if p["aos"] <= now:
            left = int((p["los"] - now).total_seconds())
            self.next_lbl.config(text=f"● LIVE  LOS in {left // 60:02d}:{left % 60:02d}", fg=self.c["good"])
        else:
            s = int((p["aos"] - now).total_seconds())
            self.next_lbl.config(text=f"NEXT  T-{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}  "
                                      f"{p['name']}  ↑{p['max_el']:.0f}°", fg=self.c["accent"])
