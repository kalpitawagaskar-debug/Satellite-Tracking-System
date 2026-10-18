"""SomaiyaSat ground-station dashboard: wires the SQLite backend to the Tkinter panels.

    python app.py --demo          # synthetic data, no internet needed
    python app.py --norad 25544   # real TLE (needs internet + skyfield); load your own CSV via the File menu

Heavy work (CSV import, TLE download, pandas) runs in TkWorker threads; widgets are only
touched on the main thread. If you already have a main window, copy the ideas, not the file.
"""
import argparse
import csv
import ctypes
import datetime as dt
import logging
import math
import random
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))   # panel files live in ui/
import analytics
import config
import detector
import health
import ingest
import passes as orbit
from db import Database, UTC, iso
from orbit_offline import ElementsCatalog
from workers import TkWorker
from dispatcher import Dispatcher, demo_network
from ui_base import PALETTE
from ground_track_panel import GroundTrackPanel, propagate_circular
from sky_view_panel import SkyViewPanel, make_demo_pass
from pass_table_panel import PassTablePanel
from waterfall_panel import WaterfallPanel
from sstv_panel import SSTVPanel
from event_log_panel import EventLogPanel
from subsystems_panel import SubsystemsPanel
from status_bar import StatusBar
from splash_screen import SplashScreen
from confusion_panel import ConfusionPanel
from scroll_frame import ScrollFrame

log = logging.getLogger("app")


def load_satellite_catalog(path=config.SATELLITE_CATALOG_PATH):
    """Return NORAD ID -> display name from the optional satellite catalog CSV."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return {
                int(row["satellite_id"]): row["satellite_name"].strip()
                for row in csv.DictReader(f)
                if row.get("satellite_id", "").strip().isdigit()
                and row.get("satellite_name", "").strip()
            }
    except OSError:
        log.info("Satellite catalog not found at %s", path)
        return {}


def load_satellite_details(path=config.SATELLITE_CATALOG_PATH):
    """Return the catalog row for each NORAD ID, for display-only orbital estimates."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return {int(row["satellite_id"]): row for row in csv.DictReader(f)
                    if row.get("satellite_id", "").strip().isdigit()}
    except OSError:
        return {}


def enable_hidpi():
    """Stops Windows from bitmap-scaling (blurring) the whole Tk window on high-DPI screens."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass


class App:
    def __init__(self, root, demo=False, norad=config.NORAD_ID):
        self.root, self.demo, self.norad = root, demo, norad
        self.satellite_catalog = load_satellite_catalog()
        self._catalog_rows = load_satellite_details()
        self.satellite_name = self._name_for(norad)
        self.db = Database(config.DB_PATH)
        self.db.init_schema()
        self.db.upsert_satellite(norad, self.satellite_name)
        self.worker = TkWorker(root)
        self.tle, self.t0, self.arc = None, 0, []
        self.elements = ElementsCatalog(config.CELESTRAK_PATH, config.SATELLITE_CATALOG_PATH)
        self.orbit_source, self._gen, self._crit_active, self.last_eval = None, 0, set(), None
        self._build_ui()
        self._build_satellite_selector()
        self._build_menu()
        self.note("INFO", "Dashboard started (demo mode)" if demo else "Dashboard started")
        self._set_mode("DEMO · SIMULATED DATA" if demo else "LOADING ORBIT…", "warn")
        self._submit_bootstrap()
        root.after(1000, self._tick_orbit)
        root.after(3000, self._poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------- UI
    def _name_for(self, norad):
        if self.demo and norad == config.NORAD_ID:
            return config.SAT_NAME
        return self.satellite_catalog.get(norad, f"NORAD {norad}")

    def _show_satellite_identity(self):
        self.root.title(f"{self.satellite_name} ({self.norad}) - SATELLITE TRACKING SYSTEM")
        if hasattr(self, "track"):
            self.track.set_satellite_name(self.satellite_name)
        if hasattr(self, "sky"):
            self.sky.set_satellite_name(self.satellite_name)
        if hasattr(self, "table"):
            self.table.set_satellite_name(self.satellite_name)
        self.bar.set_ticker(
            f"{self.satellite_name} ({self.norad})  |  M17 / CODEC2 / SSTV / TT&C  |  "
            "subsystem data shown as simulated estimates when unavailable"
        )

    def _estimated_housekeeping(self):
        """Plausible display-only values, never written to the telemetry database."""
        row = self._catalog_rows.get(self.norad, {})
        try:
            period = float(row.get("orbital_period_minutes") or 96.0) * 60.0
        except (TypeError, ValueError):
            period = 96.0 * 60.0
        phase = dt.datetime.now(UTC).timestamp() / period * 2 * math.pi + self.norad % 360
        return {
            "battery_pct": 78.0 + 12.0 * math.sin(phase - 0.7),
            "bus_v": 3.72 + 0.12 * math.sin(phase),
            "solar_w": 2.4 * max(0.0, math.sin(phase)),
            "temp_c": 24.0 + 18.0 * math.sin(phase + 0.5),
            "rssi_dbm": -112.0 + 5.0 * math.cos(phase),
        }

    def _build_ui(self):
        r = self.root
        r.title(f"{self.satellite_name} ({self.norad}) - SATELLITE TRACKING SYSTEM")
        r.configure(bg=PALETTE["bg"])
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{min(1400, sw - 40)}x{min(900, sh - 90)}")      # never taller than a small laptop screen
        r.columnconfigure(0, weight=1)
        r.rowconfigure(1, weight=1)                                  # row 0 header, row 1 scrolling page, row 2 status bar
        self.scroll = ScrollFrame(r, min_width=1180, min_height=860, bg=PALETTE["bg"])
        self.scroll.grid(row=1, column=0, sticky="nsew")
        p = self.scroll.inner
        for col, wt in enumerate((3, 2, 2)):
            p.columnconfigure(col, weight=wt, uniform="c")
        for row in range(3):
            p.rowconfigure(row, weight=3)
        g = dict(sticky="nsew", padx=6, pady=6)
        self.track = GroundTrackPanel(p, station=(config.STATION["name"], config.STATION["lat"], config.STATION["lon"]))
        self.track.grid(row=0, column=0, columnspan=2, **g)
        self.subs = SubsystemsPanel(p)
        self.subs.grid(row=0, column=2, **g)
        self.table = PassTablePanel(p)
        self.table.grid(row=1, column=0, **g)
        self.sky = SkyViewPanel(p)
        self.sky.grid(row=1, column=1, **g)
        self.log = EventLogPanel(p)
        self.log.grid(row=1, column=2, **g)
        self.wf = WaterfallPanel(p, markers=[(0.5, "M17"), (0.22, "SSTV")])
        self.wf.grid(row=2, column=0, **g)
        self.wf.start_demo()                                   # simulated RF; badge says so
        self.sstv = SSTVPanel(p)
        self.sstv.grid(row=2, column=1, **g)
        self.det = ConfusionPanel(p)
        self.det.grid(row=2, column=2, **g)
        r.minsize(640, 420)
        self.bar = StatusBar(r)
        self.bar.grid(row=2, column=0, sticky="ew")
        self.bar.set_db(True)
        self.bar.set_ticker("SOMAIYASAT  |  M17 · CODEC2 · SSTV · TT&C  |  waterfall and SSTV image are simulated")

        self._show_satellite_identity()

    def _build_satellite_selector(self):
        header = tk.Frame(self.root, bg=PALETTE["bg"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        tk.Label(header, text="SATELLITE", bg=PALETTE["bg"], fg=PALETTE["muted"],
                 font=("Consolas", 9, "bold")).pack(side="left", padx=(0, 10))
        selected = self._option_label(self.satellite_name, self.norad)
        self.satellite_options = {self._option_label(n, i): i for i, n in self.satellite_catalog.items()}
        self.satellite_options.setdefault(selected, self.norad)
        self.satellite_choice = tk.StringVar(value=selected)
        self.satellite_dropdown = ttk.Combobox(
            header, textvariable=self.satellite_choice,
            values=list(self.satellite_options), state="readonly", width=48
        )
        self.satellite_dropdown.pack(side="left")
        self.satellite_dropdown.bind("<<ComboboxSelected>>", self._on_satellite_selected)
        self.mode_badge = tk.Label(header, text="", bg=PALETTE["bg"], fg=PALETTE["warn"], font=("Consolas", 9, "bold"))
        self.mode_badge.pack(side="right")

    def _set_mode(self, text, level="warn"):
        self.mode_badge.config(text=f"● {text}", fg={"good": PALETTE["good"], "warn": PALETTE["warn"]}.get(level, PALETTE["crit"]))

    @staticmethod
    def _option_label(name, norad):
        return name if name.startswith("NORAD") else f"{name} ({norad})"

    def _refresh_satellite_options(self):
        self.satellite_options = {self._option_label(n, i): i for i, n in self.satellite_catalog.items()}
        label = self._option_label(self.satellite_name, self.norad)
        self.satellite_options.setdefault(label, self.norad)
        self.satellite_dropdown.configure(values=list(self.satellite_options))
        self.satellite_choice.set(label)

    def _on_satellite_selected(self, _event=None):
        norad = self.satellite_options.get(self.satellite_choice.get())
        if norad is None or norad == self.norad:
            return
        self.demo = False
        self.norad = norad
        self.satellite_name = self._name_for(norad)
        self.db.upsert_satellite(norad, self.satellite_name)
        label = self._option_label(self.satellite_name, norad)
        self.satellite_options.setdefault(label, norad)
        self.satellite_dropdown.configure(values=list(self.satellite_options))
        self.satellite_choice.set(label)
        self._show_satellite_identity()
        self.tle, self.arc = None, []
        self.track.clear_position("LOADING CURRENT ORBIT")
        self.sky.set_pass([])
        self.table.set_passes([])
        self.subs.clear_values()
        self.bar.set_frames(0, None)
        self._crit_active.clear()
        self._set_mode("LOADING ORBIT…", "warn")
        self.note("INFO", f"Selected {self.satellite_name} (NORAD {norad}); loading orbit")
        self._submit_bootstrap()
        self.refresh()

    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Import CSV…   Ctrl+O", command=self.import_csv)
        f.add_command(label="Load demo data", command=self.load_demo)
        f.add_separator()
        f.add_command(label="Export passes CSV…", command=self.export_passes)
        f.add_command(label="Export event log CSV…", command=self.export_events)
        f.add_separator()
        f.add_command(label="Quit   Ctrl+Q", command=self.close)
        d = tk.Menu(m, tearoff=0)
        d.add_command(label="Evaluate OPS-SAT-AD detector", command=self.evaluate_detector)
        d.add_command(label="Scan telemetry for outliers", command=self.scan_anomalies)
        d.add_command(label="Recompute orbit and passes   F5", command=self._submit_bootstrap)
        d.add_separator()
        d.add_command(label="Simulate SSTV image", command=self.sstv.start_reception)
        d.add_command(label="Run dispatch simulation", command=self.run_dispatch)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="About and data credits", command=self.show_about)
        m.add_cascade(label="File", menu=f)
        m.add_cascade(label="Data", menu=d)
        m.add_cascade(label="Help", menu=h)
        self.root.config(menu=m)
        self.root.bind_all("<Control-o>", lambda e: self.import_csv())
        self.root.bind_all("<Control-q>", lambda e: self.close())
        self.root.bind_all("<F5>", lambda e: self._submit_bootstrap())

    def note(self, level, msg):
        """Show in the event log and persist to SQLite. Main thread only."""
        self.log.log(level, msg)
        try:
            self.db.log_event(level, msg)
        except Exception:  # noqa: BLE001
            log.exception("could not persist event")

    def _failed(self, what):
        return lambda exc: self.note("CRIT", f"{what} failed: {exc}")

    # ---------------- background jobs
    def _submit_bootstrap(self):
        """Compute orbit + passes in a worker. Results from an older request are ignored."""
        self._gen += 1
        gen = self._gen
        self.worker.submit(self._bootstrap, (self.norad, self.satellite_name, self.demo),
                           on_done=lambda res: self._after_bootstrap(res, gen),
                           on_error=lambda exc: self._bootstrap_failed(exc, gen))

    def _bootstrap_failed(self, exc, gen):
        if gen != self._gen:
            return
        self.tle, self.arc, self.orbit_source = None, [], None
        self.track.clear_position("ORBIT POSITION UNAVAILABLE")
        self.sky.set_pass([])
        self.sky.cur = None
        self.sky.badge.config(text="AZ --  EL --")
        self._set_mode("NO ORBIT DATA", "crit")
        self.note("CRIT", f"orbit load failed: {exc}")

    def _ensure_ops_dataset(self):
        """Import data/dataset.csv (OPS-SAT-AD) once, so the detector panel works out of the box."""
        if self.db.ops_count(config.OPS_DATASET_NAME) == 0 and config.OPS_DATASET_PATH.exists():
            log.info("OPS-SAT-AD auto-import: %s",
                     ingest.load_ops_features(self.db, config.OPS_DATASET_PATH, config.OPS_DATASET_NAME))

    def _bootstrap(self, ctx):
        """Worker thread. ctx = (norad, display name, demo flag)."""
        norad, name, demo = ctx
        now = dt.datetime.now(UTC)
        self._ensure_ops_dataset()
        self.db.clear_future_passes(norad, now)
        if demo:
            last = self.db.last_frame_time(norad)
            if norad == config.NORAD_ID and (last is None or (now - last).total_seconds() > 1800):
                self.db.clear_telemetry(norad)      # demo satellite only: replace old demo frames
                self._seed_demo(norad)
            fake = [{"name": name, "aos": now + dt.timedelta(seconds=90 + 5400 * i),
                     "los": now + dt.timedelta(seconds=90 + 5400 * i + random.randint(300, 600)),
                     "max_el": random.choice([12, 28, 47, 63, 81])} for i in range(5)]
            self.db.save_passes(norad, fake)
            return dict(tle=None, arc=make_demo_pass(), source="DEMO", level="OK",
                        note="Demo passes generated (not a real orbit)")
        o = orbit.get_orbit(norad, name, config.TLE_CACHE_DIR, config.TLE_MAX_AGE_H, self.elements,
                            config.TLE_TIMEOUT_S)
        tle = (o["name"], o["l1"], o["l2"])
        ps = orbit.predict_passes(*tle, config.STATION, now, 48, config.MIN_ELEVATION_DEG)
        self.db.save_passes(norad, ps)
        arc = orbit.sky_track(*tle, config.STATION, ps[0]["aos"], ps[0]["los"]) if ps else []
        age = (now - o["epoch"]).total_seconds() / 86400
        stale = o["source"] in ("ARCHIVED", "APPROX", "CACHED-STALE") or age > config.STALE_ORBIT_DAYS
        note = (f"{len(ps)} passes in 48 h for {name}; orbit source {o['source']}, "
                f"element epoch {o['epoch']:%Y-%m-%d} ({age:.0f} days old)")
        if o["source"] == "APPROX":
            note += ". Only orbit SHAPE is known: positions and passes are NOT real"
        elif stale:
            note += ". Old elements: positions and passes are illustrative, not predictions"
        return dict(tle=tle, arc=arc, source=o["source"], level="WARN" if stale else "OK", note=note)

    def _seed_demo(self, norad=None):
        """Generate synthetic frames ending 'now' in the OS temp folder (never inside the project, so an
        editor or Windows cannot lock it) and load them. data/synthetic_frames.csv stays a sample for
        File > Import CSV."""
        norad = norad or self.norad
        p = Path(tempfile.gettempdir()) / "somaiyasat_demo_frames.csv"
        ingest.write_synthetic_csv(p)
        return ingest.load_csv(self.db, p, norad, config.SAT_NAME, decoder=ingest.demo_decoder)

    def _after_bootstrap(self, res, gen):
        if gen != self._gen:
            return                                   # the user already picked another satellite
        self.tle, self.arc, self.orbit_source = res["tle"], res["arc"], res["source"]
        self.sky.set_pass(self.arc)
        labels = {"DEMO": ("DEMO · SIMULATED DATA", "warn"), "LIVE": ("LIVE TLE", "good"),
                  "CACHED": ("CACHED TLE", "good"), "CACHED-STALE": ("STALE CACHED TLE", "warn"),
                  "ARCHIVED": ("ARCHIVED ELEMENTS · ILLUSTRATIVE", "warn"),
                  "APPROX": ("APPROXIMATE ORBIT · SHAPE ONLY", "crit")}
        self._set_mode(*labels.get(res["source"], (res["source"], "warn")))
        self.note(res["level"], res["note"])
        self.refresh()
        if self.last_eval is None and self.db.ops_count(config.OPS_DATASET_NAME):
            self.evaluate_detector(auto=True)

    def refresh(self):
        self.worker.submit(self._query_state, on_done=self._apply_state, on_error=self._failed("refresh"))

    def _query_state(self):
        return dict(frames=self.db.frame_count(self.norad), last=self.db.last_frame_time(self.norad),
                    values=self.db.latest_values(self.norad), passes=self.db.upcoming_passes(self.norad))

    def _apply_state(self, s):
        self.bar.set_frames(s["frames"], s["last"])
        measured = s["values"]
        values = {**self._estimated_housekeeping(), **measured}
        self.subs.update_values(values)
        rep = health.assess(values, config.THRESHOLDS, s["last"])
        if not measured:
            source = "SIMULATED"
        elif set(values) - set(measured):
            source = "MEASURED+SIM"
        else:
            source = "IMPORTED"
        self.subs.badge.config(text=f"HEALTH {rep.score:.0f} {rep.status} · {source}",
                               fg={"OK": self.subs.c["good"], "WARN": self.subs.c["warn"]}.get(rep.status, self.subs.c["crit"]))
        self.table.set_passes([{**p, "name": self.satellite_name} for p in s["passes"]])
        crit_now = set()
        for metric, v in s["values"].items():
            lim = config.THRESHOLDS.get(metric)
            if lim and ((lim["bad_when"] == "low" and v <= lim["crit"]) or (lim["bad_when"] == "high" and v >= lim["crit"])):
                crit_now.add(metric)
        for metric in sorted(crit_now - self._crit_active):
            self.note("CRIT", f"{metric} = {s['values'][metric]:.1f} beyond critical limit")
        for metric in sorted(self._crit_active - crit_now):
            self.note("OK", f"{metric} is back inside its limits")
        self._crit_active = crit_now

    def _poll(self):
        self.refresh()
        self.root.after(3000, self._poll)

    def import_csv(self):
        path = filedialog.askopenfilename(title="Import CSV", filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not path:
            return
        name = Path(path).name
        try:
            kind, header = ingest.sniff_csv(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            self.note("CRIT", f"cannot read {name}: {exc}")
            return
        if kind == "ops_features":
            self.note("INFO", f"{name}: OPS-SAT-AD segment features detected, importing")
            self.worker.submit(ingest.load_ops_features, self.db, path, config.OPS_DATASET_NAME,
                               on_done=self._ops_imported, on_error=self._failed("OPS-SAT-AD import"))
        elif kind == "celestrak_elements":
            self.elements.reload(celestrak_path=path)
            self.note("OK", f"{name}: orbital elements loaded for offline orbits (this session)")
            self._submit_bootstrap()
        elif kind == "catalog":
            self.satellite_catalog, self._catalog_rows = load_satellite_catalog(path), load_satellite_details(path)
            self.elements.reload(catalog_path=path)
            self._refresh_satellite_options()
            self.note("OK", f"{name}: {len(self.satellite_catalog)} satellites loaded into the selector")
        elif kind == "frames":
            self._import_frames(path)
        else:
            self.note("CRIT", f"{name}: unrecognised CSV. First columns: {header[:6]}")
            messagebox.showwarning("Unrecognised CSV", "Expected one of: telemetry frames (timestamp + hex), "
                                   "OPS-SAT-AD features, orbital elements or a satellite catalogue.\n\n"
                                   f"This file starts with: {header[:8]}")

    def _ops_imported(self, st):
        self.note("OK", f"OPS-SAT-AD: {st['inserted']} new segments ({st['read']} read, {st['bad']} bad rows skipped)")
        self.evaluate_detector()

    def _import_frames(self, path):
        norad = simpledialog.askinteger("NORAD ID", "NORAD ID of this satellite:", initialvalue=self.norad,
                                        minvalue=1, maxvalue=999999, parent=self.root)
        if not norad:
            return
        self.note("INFO", f"Importing {Path(path).name} …")
        self.norad = norad
        self.satellite_name = self._name_for(norad)
        self.db.upsert_satellite(norad, self.satellite_name)
        self._show_satellite_identity()
        self._refresh_satellite_options()
        decoder = ingest.demo_decoder if self.demo else None
        self.worker.submit(ingest.load_csv, self.db, path, norad, decoder=decoder,
                           on_done=self._imported, on_error=self._failed("import"))
        if not self.demo:
            self.tle, self.arc = None, []
            self._submit_bootstrap()

    def _imported(self, st):
        self.note("OK", f"Imported {st['inserted']} new frames ({st['bad']} bad rows skipped)")
        if st["housekeeping"] == 0:
            self.note("WARN", "No housekeeping decoded: raw hex needs a satellite-specific decoder")
        self.refresh()

    def load_demo(self):
        self.demo = True
        self._set_mode("DEMO · SIMULATED DATA", "warn")
        self.worker.submit(self._seed_demo, on_done=lambda s: (self.note("OK", f"Demo data: {s['inserted']} new frames"),
                                                               self.refresh()), on_error=self._failed("demo load"))

    def scan_anomalies(self):
        def job():
            out = {}
            for metric, lim in config.THRESHOLDS.items():
                rows = self.db.metric_series(self.norad, metric)
                if len(rows) > 30:
                    df = analytics.flag_anomalies(analytics.series_frame(rows))
                    out[metric] = (int(df["anomaly"].sum()), analytics.limit_violations(df, lim["warn"], lim["crit"], lim["bad_when"]))
            return out
        self.worker.submit(job, on_done=self._scan_done, on_error=self._failed("anomaly scan"))

    def _scan_done(self, res):
        if not res:
            self.note("WARN", "Not enough housekeeping data to scan (need > 30 points)")
        for metric, (n, lim) in res.items():
            self.note("WARN" if n or lim["crit"] else "OK",
                      f"{metric}: {n} outliers vs local trend, {lim['warn']} warn / {lim['crit']} crit samples")

    def run_dispatch(self):
        res = Dispatcher(demo_network(random.randint(1, 999))).dispatch("GS", "SOMAIYAPOD")
        self.note("INFO", "DISPATCH (SIMULATED network, made-up distances)")
        for line in res.summary():
            self.note("OK" if "DELIVERED" in line and "NOT" not in line else "WARN" if "FAIL" in line or "NOT" in line else "INFO", line.strip())

    def evaluate_detector(self, auto=False):
        self.det.show_message("Evaluating…")

        def job():
            self._ensure_ops_dataset()
            return detector.evaluate_rows(self.db.ops_segments(config.OPS_DATASET_NAME))
        self.worker.submit(job, on_done=lambda r: self._eval_done(r, auto), on_error=self._eval_failed)

    def _eval_done(self, r, auto):
        self.last_eval = r
        self.det.show(r)
        m = r["model"]
        self.note("OK", f"OPS-SAT-AD detector, {r['n_test']} test segments: F1 {m['f1']:.2f}, "
                        f"precision {m['precision']:.2f}, recall {m['recall']:.2f}")
        if not auto:
            self.note("INFO", "Benchmark data from ESA OPS-SAT, not SomaiyaSat telemetry")

    def _eval_failed(self, exc):
        self.det.show_message(f"Evaluation failed:\n{exc}")
        self.note("CRIT", f"detector failed: {exc}")

    def export_passes(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="passes.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = self.db.upcoming_passes(self.norad, limit=200)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["satellite", "norad_id", "aos_utc", "los_utc", "max_elevation_deg", "orbit_source"])
            for p in rows:
                w.writerow([self.satellite_name, self.norad, iso(p["aos"]), iso(p["los"]),
                            f"{p['max_el']:.1f}", self.orbit_source or ""])
        self.note("OK", f"Exported {len(rows)} passes to {Path(path).name}")

    def export_events(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="events.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = self.db.recent_events(100000)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time_utc", "level", "message"])
            w.writerows(rows)
        self.note("OK", f"Exported {len(rows)} events to {Path(path).name}")

    def show_about(self):
        messagebox.showinfo("About and data credits", (
            "Satellite Tracking System: ground-station dashboard (Tkinter + SQLite).\n\n"
            "REAL DATA\n"
            "- OPS-SAT-AD segment features (ESA OPS-SAT benchmark, data/dataset.csv)\n"
            "- Orbital elements and catalogue CSVs in data/ (archived, months old)\n\n"
            "SIMULATED\n"
            "- Demo orbit and telemetry, RF waterfall, SSTV image, dispatch network,\n"
            "  subsystem estimates and all example health limits\n\n"
            "Routing is classical shortest-path, not machine learning.\n"
            "See DATA_SOURCES.md for licences. Credit the data authors."), parent=self.root)

    # ---------------- 1 Hz animation
    def _tick_orbit(self):
        self.t0 += 1
        try:
            if self.tle:
                lat, lon, alt = orbit.subpoint(*self.tle)
                self.track.update_position(lat, lon, alt)
                if self.orbit_source in ("ARCHIVED", "APPROX", "CACHED-STALE"):
                    self.track.badge.config(text=self.track.badge.cget("text") + f"  {self.orbit_source}")
                az, el = orbit.azel_now(*self.tle, config.STATION)
                self.sky.cur = (az, el) if el > 0 else None
                self.sky.badge.config(text=f"AZ {az:5.1f}  EL {el:5.1f}")
            elif self.demo:
                lat, lon = propagate_circular(self.t0 * 20 + 1500)
                self.track.update_position(lat, lon, 550)
                self.track.badge.config(text=self.track.badge.cget("text") + "  DEMO ORBIT")
                if self.arc:
                    self.sky.set_position(*self.arc[(self.t0 // 1) % len(self.arc)])
            elif self.track.pos:
                self.track.clear_position()
                self.sky.cur = None
        except Exception:  # noqa: BLE001
            log.exception("orbit tick failed")
        self.root.after(1000, self._tick_orbit)

    def close(self):
        self.worker.shutdown()
        self.db.close_all()
        self.root.destroy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--norad", type=int, default=config.NORAD_ID)
    ap.add_argument("--no-splash", action="store_true")
    a = ap.parse_args()
    config.setup_logging()
    enable_hidpi()
    root = tk.Tk()
    root.report_callback_exception = lambda *e: (log.error("Tk callback error", exc_info=e),
                                                 messagebox.showerror("Error", str(e[1])))
    root.withdraw()
    App(root, demo=a.demo, norad=a.norad)
    if a.no_splash:
        root.deiconify()
    else:
        SplashScreen(root, on_done=root.deiconify)
    root.mainloop()


if __name__ == "__main__":
    main()
