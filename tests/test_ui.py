"""GUI tests (skipped automatically when no display is available).
Run:  python -m unittest discover -s tests -v"""
import os
import sys
import types
import tkinter as tk
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ui"))
from scroll_frame import ScrollFrame


def make_root(w, h):
    try:
        r = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest("no display available")
    r.geometry(f"{w}x{h}")
    return r


def wheel(sf, delta, shift=False):
    sf.update()
    ev = types.SimpleNamespace(type=tk.EventType.MouseWheel, x_root=sf.canvas.winfo_rootx() + 50,
                               y_root=sf.canvas.winfo_rooty() + 50, delta=delta, num=0, state=1 if shift else 0, keysym="")
    sf._on_key_or_wheel(ev)
    sf.update()


class ScrollFrameTests(unittest.TestCase):
    def test_small_window_scrolls_big_window_does_not(self):
        r = make_root(700, 450)
        self.addCleanup(r.destroy)
        r.columnconfigure(0, weight=1); r.rowconfigure(0, weight=1)
        sf = ScrollFrame(r, min_width=1180, min_height=860)
        sf.grid(sticky="nsew")
        tk.Label(sf.inner, text="x").pack()
        r.update()
        self.assertTrue(sf.vbar.winfo_ismapped() and sf.hbar.winfo_ismapped())
        self.assertEqual([int(v) for v in sf.canvas.cget("scrollregion").split()], [0, 0, 1180, 860])
        self.assertEqual(sf.canvas.yview()[0], 0.0)
        wheel(sf, -120)                                   # wheel down
        self.assertGreater(sf.canvas.yview()[0], 0.0)
        wheel(sf, 120)
        self.assertEqual(sf.canvas.yview()[0], 0.0)
        wheel(sf, -120, shift=True)                       # Shift+wheel = sideways
        self.assertGreater(sf.canvas.xview()[0], 0.0)
        r.geometry("1500x1000")
        r.update()
        self.assertFalse(sf.vbar.winfo_ismapped() or sf.hbar.winfo_ismapped())
        self.assertGreaterEqual(sf.inner.winfo_width(), 1400)       # content stretches to fill the window

    def test_wheel_over_text_widget_does_not_scroll_page(self):
        r = make_root(700, 450)
        self.addCleanup(r.destroy)
        r.columnconfigure(0, weight=1); r.rowconfigure(0, weight=1)
        sf = ScrollFrame(r, min_width=1180, min_height=860)
        sf.grid(sticky="nsew")
        t = tk.Text(sf.inner)
        t.place(x=0, y=0, width=600, height=300)
        r.update()
        ev = types.SimpleNamespace(type=tk.EventType.MouseWheel, x_root=t.winfo_rootx() + 20, y_root=t.winfo_rooty() + 20,
                                   delta=-120, num=0, state=0, keysym="")
        sf._on_key_or_wheel(ev)
        self.assertEqual(sf.canvas.yview()[0], 0.0)


class DropdownRegressionTests(unittest.TestCase):
    def test_wheel_over_open_combobox_list_does_not_crash(self):
        """Real bug on Windows/Python 3.14: KeyError 'popdown' while the satellite list was open."""
        from tkinter import ttk
        r = make_root(700, 450)
        self.addCleanup(r.destroy)
        r.columnconfigure(0, weight=1); r.rowconfigure(0, weight=1)
        sf = ScrollFrame(r, min_width=1180, min_height=860)
        sf.grid(sticky="nsew")
        cb = ttk.Combobox(sf.inner, values=["a", "b", "c"], state="readonly")
        cb.place(x=10, y=10)
        r.update()
        r.tk.call("ttk::combobox::Post", cb)
        r.update()
        pop = f"{cb}.popdown"
        ev = types.SimpleNamespace(type=tk.EventType.MouseWheel, x_root=int(r.tk.call("winfo", "rootx", pop)) + 10,
                                   y_root=int(r.tk.call("winfo", "rooty", pop)) + 10, delta=-120, num=0, state=0, keysym="")
        sf._on_key_or_wheel(ev)                          # must not raise
        self.assertEqual(sf.canvas.yview()[0], 0.0)      # and must not scroll the page behind the list


class AppScrollTests(unittest.TestCase):
    def test_dashboard_on_a_small_screen_can_scroll_to_every_panel(self):
        import tempfile
        import config
        config.DB_PATH = config.Path(tempfile.mkdtemp()) / "t.db"          # never touch the real database
        import app
        import gc
        self.addCleanup(gc.collect)          # runs LAST, on the main thread: frees the old window here, never in a worker thread
        r = make_root(800, 500)
        self.addCleanup(r.destroy)
        a = app.App(r, demo=True)
        self.addCleanup(lambda: (a.worker.shutdown(), a.worker._pool.shutdown(wait=True)))   # runs FIRST: no threads left
        r.geometry("800x500")
        for _ in range(5):
            r.update()
        sc = a.scroll
        self.assertTrue(sc.vbar.winfo_ismapped())
        self.assertLessEqual(a.bar.winfo_rooty() + a.bar.winfo_height(), r.winfo_rooty() + r.winfo_height() + 2)   # status bar stays visible
        sc.canvas.yview_moveto(1.0)
        r.update()
        page_bottom = sc.canvas.winfo_rooty() + sc.canvas.winfo_height()
        for panel in (a.wf, a.sstv, a.det):                                  # the bottom row was unreachable before
            self.assertLessEqual(panel.winfo_rooty() + panel.winfo_height(), page_bottom + 2)
            self.assertGreaterEqual(panel.winfo_rooty() + panel.winfo_height(), sc.canvas.winfo_rooty())


if __name__ == "__main__":
    unittest.main()
