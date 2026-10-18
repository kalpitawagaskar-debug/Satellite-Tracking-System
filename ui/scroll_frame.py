"""Scrollable page: vertical + horizontal scrollbars, mouse wheel, Shift+wheel, PageUp/PageDown.
Put your widgets in .inner. When the window is bigger than min_width x min_height the content
stretches to fill it and the scrollbars disappear; when smaller, the content keeps its size and scrolls."""
import sys
import tkinter as tk
from tkinter import ttk

NO_WHEEL = (tk.Text, tk.Listbox, ttk.Treeview)      # these scroll themselves: do not scroll the page too


class ScrollFrame(tk.Frame):
    def __init__(self, master, min_width=1180, min_height=860, bg="#0a0e17"):
        super().__init__(master, bg=bg)
        self.min_w, self.min_h = min_width, min_height
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, yscrollincrement=20, xscrollincrement=20)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=lambda a, b: self._set(self.vbar, 0, a, b),
                              xscrollcommand=lambda a, b: self._set(self.hbar, 1, a, b))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self._fit())
        self.inner.bind("<Configure>", lambda e: self._fit())
        for seq in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>",
                    "<Shift-Button-4>", "<Shift-Button-5>", "<Prior>", "<Next>"):
            self.bind_all(seq, self._on_key_or_wheel, add="+")

    def _set(self, bar, col, lo, hi):
        """Show a scrollbar only while it is needed."""
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            bar.grid_remove()
        else:
            bar.grid(row=0 if col == 0 else 1, column=1 if col == 0 else 0, sticky="ns" if col == 0 else "ew")
        bar.set(lo, hi)

    def _fit(self):
        w = max(self.canvas.winfo_width(), self.min_w)
        h = max(self.canvas.winfo_height(), self.min_h)
        self.canvas.itemconfigure(self._win, width=w, height=h)
        self.canvas.configure(scrollregion=(0, 0, w, h))

    def _inside(self, widget):
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_key_or_wheel(self, e):
        w = None
        if e.type in (tk.EventType.MouseWheel, tk.EventType.ButtonPress):
            try:
                w = self.winfo_containing(e.x_root, e.y_root)
            except (KeyError, tk.TclError):
                return          # pointer is over a Tk-internal window (e.g. the dropdown list): not ours to scroll
        if e.type in (tk.EventType.MouseWheel, tk.EventType.ButtonPress):
            if not self._inside(w) or isinstance(w, NO_WHEEL):
                return
            if getattr(e, "num", 0) == 4:
                step = -3
            elif getattr(e, "num", 0) == 5:
                step = 3
            else:
                step = -e.delta if sys.platform == "darwin" else -int(e.delta / 120) * 3
            horizontal = bool(e.state & 0x0001)                       # Shift held
            (self.canvas.xview_scroll if horizontal else self.canvas.yview_scroll)(step, "units")
        elif e.keysym in ("Prior", "Next") and not isinstance(self.focus_get(), (tk.Text, tk.Entry, ttk.Combobox)):
            self.canvas.yview_scroll(-1 if e.keysym == "Prior" else 1, "pages")
