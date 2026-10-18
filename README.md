# Satellite Tracking System (Tkinter + SQLite)

Ground-station dashboard for the SomaiyaSat / SomaiyaPod PocketQube mission idea: pass schedule, ground track,
sky view, subsystem health, event log, RF waterfall, SSTV receiver and an **anomaly detector** trained on real
ESA OPS-SAT telemetry features. Everything is stored in a SQLite database.

## Run in VS Code
1. Unzip, then **File > Open Folder** on this folder. Python 3.9+ from python.org (includes Tkinter; check `python -m tkinter`).
2. Terminal (Ctrl+`):
   ```
   python -m venv .venv
   .venv\Scripts\activate            (Windows)    |    source .venv/bin/activate    (macOS/Linux)
   pip install -r requirements.txt
   python app.py --demo
   ```
   or press **F5** and pick a configuration. Other launches: `python app.py --norad 27848` (CubeSat CO-57), `--no-splash`.
3. Tests: `python -m unittest discover -s tests -v`
4. Problems? `python check_env.py` shows which Python VS Code uses and what is missing. Always install with
   `python -m pip install -r requirements.txt` so the packages go into the same Python that runs the app.
   `ModuleNotFoundError: skyfield` only affects real satellites; `--demo` works without it.

## Small screen? Scroll
The dashboard scrolls: mouse wheel (vertical), Shift + wheel (sideways), PageUp / PageDown, or the scrollbars. On a large
screen the scrollbars disappear. The menu, satellite selector and status bar stay in place.

## What each menu item does
| Menu | Function |
|---|---|
| File > Import CSV | Detects the file type from its header: telemetry frames (asks for NORAD ID), OPS-SAT-AD features, orbital elements, or satellite catalogue. Anything else gets a clear message |
| File > Load demo data / Export passes / Export event log | Synthetic frames ending "now"; CSV exports |
| Data > Evaluate OPS-SAT-AD detector | Trains on the supplied train split, scores the test split, draws the confusion matrix |
| Data > Scan telemetry for outliers | Flags points that jump away from the local trend |
| Data > Recompute orbit and passes (F5) | Live TLE, else cached, else archived elements from `data/` |
| Data > Simulate SSTV / Run dispatch simulation | Simulated demos |
| Satellite selector | 62 satellites from `data/satellite_catalog.csv`; the badge top-right shows where the orbit came from |

## Orbit sources (badge top-right)
LIVE / CACHED TLE: real. **ARCHIVED ELEMENTS**: from `data/celestrak_satellite_dataset_3-April-2026.csv`, months old, so
positions and passes are *illustrative*, not predictions. **APPROXIMATE ORBIT**: only the orbit shape is known. DEMO: toy orbit.

## Measured on the supplied OPS-SAT-AD file (`data/dataset.csv`, 2,123 segments, 9 channels)
Test split 529 segments (113 anomalous): precision 0.86, recall 0.91, F1 0.88. A detector that never alarms scores 79 % accuracy,
and an unsupervised z-score scores F1 0.21. Without segment-length features F1 is 0.81. This is ESA OPS-SAT data, not SomaiyaSat,
and the split is random, so expect lower scores on a new satellite.

## Layout
```
app.py  config.py  db.py + schema.sql  ingest.py  passes.py  orbit_offline.py  analytics.py  detector.py
health.py  routing.py  dispatcher.py  workers.py  release.py        ui/ (panels)   tests/   data/ (CSV inputs)
```

## Honest limits
- Simulated: demo orbit/telemetry, waterfall, SSTV image, dispatch network, subsystem estimates, all health limits (examples only).
- Routing is classical shortest-path (Yen's k-best), not machine learning.
- Real SatNOGS frame CSVs are raw hex: battery/temperature need a decoder for that satellite. Column names were not checked against a real export.
- The live CelesTrak download was not testable where this was built; the offline fallback was.
- The outlier scan assumes slow trends compared with its 21-sample window; fast oscillations would false-alarm.
- Built and tested on Python 3.12 / Linux with a virtual display. Not tested on Windows or macOS.

Licences and data credits: see DATA_SOURCES.md.
