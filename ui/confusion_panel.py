"""Anomaly-detector report card: confusion matrix + metrics + honest reference lines.
Feed it the dict returned by detector.evaluate_rows()."""
import tkinter as tk
from ui_base import BasePanel, mono, mix


class ConfusionPanel(BasePanel):
    def __init__(self, master, colors=None, **kw):
        super().__init__(master, "Anomaly detector", "OPS-SAT-AD benchmark", colors, **kw)
        self.cv = tk.Canvas(self.body, bg=self.c["panel"], highlightthickness=0, width=380, height=300)
        self.cv.pack(fill="both", expand=True)
        self.res, self.msg = None, "No evaluation yet.\nData > Evaluate OPS-SAT-AD detector"
        self.cv.bind("<Configure>", lambda e: self._draw())

    def show_message(self, text):
        self.res, self.msg = None, text
        self._draw()

    def show(self, result):
        self.res = result
        self._draw()

    def _draw(self):
        cv, c = self.cv, self.c
        cv.delete("all")
        w, h = max(cv.winfo_width(), 300), max(cv.winfo_height(), 200)
        if not self.res:
            cv.create_text(w / 2, h / 2, text=self.msg, fill=c["muted"], font=mono(9), justify="center")
            return
        r, m = self.res, self.res["model"]
        cell = max(46, min(70, (h - 120) // 2, (w - 170) // 2))
        x0, y0 = 62, 30
        cv.create_text(x0 + cell, 8, text="PREDICTED", fill=c["muted"], font=mono(7, True))
        for i, t in enumerate(("normal", "anomaly")):
            cv.create_text(x0 + cell * i + cell / 2 - 1, 21, text=t, fill=c["muted"], font=mono(7))
            cv.create_text(x0 - 5, y0 + cell * i + cell / 2, text=t, fill=c["muted"], anchor="e", font=mono(7))
        cv.create_text(7, y0 + cell, text="ACTUAL", fill=c["muted"], font=mono(7, True), angle=90)
        top = max(m["tn"], m["fp"], m["fn"], m["tp"], 1)
        for (row, col), key, good in (((0, 0), "tn", True), ((0, 1), "fp", False),
                                      ((1, 0), "fn", False), ((1, 1), "tp", True)):
            fill = mix(c["panel2"], c["good"] if good else c["crit"], 0.15 + 0.6 * m[key] / top)
            x, y = x0 + col * cell, y0 + row * cell
            cv.create_rectangle(x, y, x + cell - 3, y + cell - 3, fill=fill, outline=c["border"])
            cv.create_text(x + cell / 2 - 1, y + cell / 2 - 1, text=str(m[key]), fill="white", font=mono(12, True))
        tx = x0 + 2 * cell + 14
        for i, (k, v) in enumerate((("PRECISION", m["precision"]), ("RECALL", m["recall"]),
                                    ("F1", m["f1"]), ("ACCURACY", m["accuracy"]))):
            yy = y0 + 8 + i * (cell * 2 - 8) / 3.4
            cv.create_text(tx, yy, text=k, fill=c["muted"], anchor="w", font=mono(7, True))
            cv.create_text(w - 10, yy, text=f"{v:.2f}", fill=c["accent"], anchor="e", font=mono(10, True))
        ns = r.get("without_size_features")
        notes = [f"{r['n_test']} test / {r['n_train']} train, {r['anomaly_rate_test']:.0%} anomalous",
                 f"never-alarm baseline accuracy {r['always_nominal_accuracy']:.0%}",
                 f"unsupervised z-score F1 {r['unsupervised']['f1']:.2f}"]
        if ns:
            notes.append(f"without length features F1 {ns['f1']:.2f}")
        y = y0 + 2 * cell + 8
        for t in notes:
            cv.create_text(8, y, text=t, fill=c["text"], anchor="nw", font=mono(8))
            y += 13
        cv.create_text(8, y + 2, text="ESA OPS-SAT data, not SomaiyaSat", fill=c["warn"], anchor="nw", font=mono(8))
