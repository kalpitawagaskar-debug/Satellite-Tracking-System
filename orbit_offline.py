"""Offline orbit source: build a valid TLE from the orbital elements stored in your CSV files.

 * ARCHIVED : full elements found by name in the CelesTrak CSV (epoch 2026-03/04 in your file).
 * APPROX   : only inclination, eccentricity and mean motion from satellite_catalog.csv are known;
              RAAN, argument of perigee and phase are ARBITRARY. The orbit SHAPE is right, the position is not.
Both sources are old. Do not treat the positions or passes as predictions.
bstar (drag) is unknown and set to 0, so error grows with time since the epoch.
"""
import csv
import datetime as dt
import math
import threading

UTC = dt.timezone.utc


def make_tle(name, norad, epoch, inc, raan, ecc, argp, ma, mean_motion):
    """Elements (degrees, rev/day, aware or naive-UTC epoch) -> (name, line1, line2)."""
    try:
        from sgp4.api import Satrec, WGS72
        from sgp4.exporter import export_tle
    except ImportError as exc:
        from passes import TLEError, missing_package_message
        raise TLEError(missing_package_message()) from exc
    epoch = epoch if epoch.tzinfo else epoch.replace(tzinfo=UTC)
    days = (epoch - dt.datetime(1949, 12, 31, tzinfo=UTC)).total_seconds() / 86400
    sat = Satrec()
    sat.sgp4init(WGS72, "i", int(norad), days, 0.0, 0.0, 0.0, float(ecc), math.radians(argp),
                 math.radians(inc), math.radians(ma), mean_motion * 2 * math.pi / 1440, math.radians(raan))
    l1, l2 = export_tle(sat)
    return name, l1, l2


def _parse_epoch(s):
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


class ElementsCatalog:
    """Lazy, thread-safe loader for the two CSV files."""

    def __init__(self, celestrak_path=None, catalog_path=None):
        self.celestrak_path, self.catalog_path = celestrak_path, catalog_path
        self._by_name, self._catalog, self._loaded = {}, {}, False
        self._lock = threading.Lock()

    def reload(self, celestrak_path=None, catalog_path=None):
        with self._lock:
            self.celestrak_path = celestrak_path or self.celestrak_path
            self.catalog_path = catalog_path or self.catalog_path
            self._loaded = False

    def _load(self):
        with self._lock:
            if self._loaded:
                return
            self._by_name, self._catalog = {}, {}
            try:
                with open(self.celestrak_path, newline="", encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        self._by_name.setdefault(r["name"].strip(), []).append(r)
            except (OSError, TypeError):
                pass
            try:
                with open(self.catalog_path, newline="", encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        if r.get("satellite_id", "").strip().isdigit():
                            self._catalog[int(r["satellite_id"])] = r
            except (OSError, TypeError):
                pass
            self._loaded = True

    def names(self):
        self._load()
        return {n: r.get("satellite_name", "").strip() for n, r in self._catalog.items()}

    def tle_for(self, norad, name=None):
        """dict(name,l1,l2,source,epoch) or None when nothing is known about this satellite."""
        self._load()
        cat = self._catalog.get(int(norad))
        name = name or (cat["satellite_name"].strip() if cat else None)
        rows = self._by_name.get(name or "", [])
        try:
            if rows:
                if cat and len(rows) > 1:      # duplicates: take the row closest to the catalogue values
                    ci, cm = float(cat["inclination_deg"]), float(cat["mean_motion_rev_per_day"])
                    rows = sorted(rows, key=lambda r: abs(float(r["inclination_deg"]) - ci)
                                  + abs(float(r["mean_motion_rev_per_day"]) - cm))
                r, ep = rows[0], _parse_epoch(rows[0]["epoch"])
                n, l1, l2 = make_tle(name, norad, ep, float(r["inclination_deg"]), float(r["raan_deg"]),
                                     float(r["eccentricity"]), float(r["arg_perigee_deg"]),
                                     float(r["mean_anomaly_deg"]), float(r["mean_motion_rev_per_day"]))
                return dict(name=n, l1=l1, l2=l2, source="ARCHIVED", epoch=ep)
            if cat:
                ep = _parse_epoch(cat["tle_epoch_utc"])
                n, l1, l2 = make_tle(name, norad, ep, float(cat["inclination_deg"]), (int(norad) * 7) % 360,
                                     float(cat["eccentricity"]), 0.0, int(norad) % 360,
                                     float(cat["mean_motion_rev_per_day"]))
                return dict(name=n, l1=l1, l2=l2, source="APPROX", epoch=ep)
        except (ValueError, KeyError):
            return None
        return None
