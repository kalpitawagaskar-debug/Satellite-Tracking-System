"""Preview of all new panels with simulated data. Run: python demo_new_panels.py"""
import datetime as dt
import random
import tkinter as tk
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


def build(root):
    root.title("SomaiyaSat - new panels preview")
    root.configure(bg=PALETTE["bg"])
    root.geometry("1400x860")
    for col, wt in enumerate((3, 2, 2)):
        root.columnconfigure(col, weight=wt, uniform="c")
    root.rowconfigure(0, weight=3)
    root.rowconfigure(1, weight=3)
    track = GroundTrackPanel(root); track.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
    subs = SubsystemsPanel(root); subs.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
    passes = PassTablePanel(root); passes.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
    sky = SkyViewPanel(root); sky.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
    log = EventLogPanel(root); log.grid(row=1, column=2, sticky="nsew", padx=6, pady=6)
    wf = WaterfallPanel(root, markers=[(0.5, "M17"), (0.22, "SSTV")]); wf.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
    sstv = SSTVPanel(root); sstv.grid(row=2, column=1, columnspan=2, sticky="nsw", padx=6, pady=6)
    root.rowconfigure(2, weight=3)
    bar = StatusBar(root); bar.grid(row=3, column=0, columnspan=3, sticky="ew")
    bar.set_db(True)
    bar.set_ticker("SOMAIYASAT DEMO  |  all values simulated  |  M17 · CODEC2 · SSTV · TT&C  |  "
                   "replace simulators with SQLite queries")

    now = dt.datetime.now(dt.timezone.utc)
    passes.set_passes([
        {"name": "SOMAIYASAT", "aos": now + dt.timedelta(seconds=90 + 5400 * i),
         "los": now + dt.timedelta(seconds=90 + 5400 * i + random.randint(300, 600)),
         "max_el": random.choice([12, 28, 47, 63, 81])} for i in range(5)])
    sky.set_pass(make_demo_pass())
    wf.start_demo()
    state = {"t": 0, "n": 0, "last": None}

    def step():
        state["t"] += 20
        lat, lon = propagate_circular(state["t"] + 1500)
        track.update_position(lat, lon, 550)
        k = (state["t"] // 20) % 61
        arc = sky.arc[k]
        sky.set_position(*arc)
        subs.update_values({"battery_pct": 70 + 15 * random.random(), "bus_v": 3.9 + 0.1 * random.random(),
                            "solar_w": max(0, 2.2 + random.uniform(-0.4, 0.4)),
                            "temp_c": 30 + 25 * random.random() ** 2, "rssi_dbm": -118 + random.uniform(-14, 10)})
        if random.random() < 0.5:
            state["n"] += 1
            state["last"] = dt.datetime.now(dt.timezone.utc)
            bar.set_frames(state["n"], state["last"])
            log.log(random.choice(["RX", "RX", "INFO", "OK", "WARN", "CRIT"]), random.choice([
                "Beacon frame decoded (CRC ok)", "AOS: carrier lock", "Battery below warn threshold",
                "SSTV line sync lost", "Telemetry stored to SQLite", "Doppler correction applied"]))
        root.after(1000, step)
    step()
    root.after(2500, sstv.start_reception)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    build(root)
    SplashScreen(root, on_done=root.deiconify)
    root.mainloop()
