"""Single place for paths, ground-station location, thresholds and logging."""
import logging
import logging.handlers
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DB_PATH = DATA_DIR / "somaiyasat.db"
SATELLITE_CATALOG_PATH = DATA_DIR / "satellite_catalog.csv"
CELESTRAK_PATH = DATA_DIR / "celestrak_satellite_dataset_3-April-2026.csv"   # archived orbital elements
OPS_DATASET_PATH = DATA_DIR / "dataset.csv"                                  # OPS-SAT-AD features
OPS_DATASET_NAME = "OPSSAT-AD"
TLE_CACHE_DIR = DATA_DIR / "tle_cache"
LOG_PATH = DATA_DIR / "app.log"

# Approximate Vidyavihar, Mumbai. EDIT to your real antenna coordinates.
STATION = {"name": "MUMBAI GS", "lat": 19.08, "lon": 72.90, "alt_m": 10}

# NORAD ID of the satellite you analyse. 99999 is the placeholder used by demo data.
NORAD_ID = 99999
SAT_NAME = "SOMAIYASAT"

TLE_MAX_AGE_H = 72
TLE_TIMEOUT_S = 6          # short, so an offline PC falls back to archived elements quickly
STALE_ORBIT_DAYS = 14      # older elements than this are labelled "illustrative"
MIN_ELEVATION_DEG = 10

# Example limits. Replace with real design limits before presenting them as mission limits.
THRESHOLDS = {
    "battery_pct": dict(warn=30, crit=15, bad_when="low"),
    "bus_v": dict(warn=3.5, crit=3.3, bad_when="low"),
    "temp_c": dict(warn=55, crit=70, bad_when="high"),
    "rssi_dbm": dict(warn=-120, crit=-130, bad_when="low"),
}


def setup_logging(level=logging.INFO):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(level)
