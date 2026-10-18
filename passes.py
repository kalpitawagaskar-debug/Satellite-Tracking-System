"""TLE download (cached) and pass prediction with Skyfield. Skyfield is NOT in your syllabus:
pip install skyfield. fetch_tle() was not tested against the live server from my sandbox.
"""
import sys
import time
import datetime as dt
import urllib.request
from pathlib import Path

UTC = dt.timezone.utc
CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=tle"


from workers import UserFacingError


class TLEError(UserFacingError):
    pass


def fetch_tle_ex(norad, cache_dir, max_age_h=72, timeout=6):
    """Return (name, line1, line2, source) with source LIVE, CACHED or CACHED-STALE.
    Fresh cache file first; otherwise the network; on failure a stale cache; else TLEError."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{norad}.tle"
    if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
        return (*_parse(f.read_text()), "CACHED")
    try:
        req = urllib.request.Request(CELESTRAK.format(norad=norad), headers={"User-Agent": "SomaiyaSat-student"})
        text = urllib.request.urlopen(req, timeout=timeout).read().decode()
        out = _parse(text)
        f.write_text(text)
        return (*out, "LIVE")
    except Exception as exc:  # noqa: BLE001
        if f.exists():
            return (*_parse(f.read_text()), "CACHED-STALE")
        raise TLEError(f"cannot fetch TLE for {norad}: {exc}") from exc


def fetch_tle(norad, cache_dir, max_age_h=72, timeout=6):
    """Backwards-compatible 3-tuple version of fetch_tle_ex."""
    return fetch_tle_ex(norad, cache_dir, max_age_h, timeout)[:3]


def tle_epoch(line1):
    """Epoch of a TLE as an aware UTC datetime."""
    yy, day = int(line1[18:20]), float(line1[20:32])
    year = 2000 + yy if yy < 57 else 1900 + yy
    return dt.datetime(year, 1, 1, tzinfo=UTC) + dt.timedelta(days=day - 1)


def get_orbit(norad, name, cache_dir, max_age_h=72, catalog=None, timeout=6):
    """Best available orbit: live/cached TLE, else archived elements from the local CSV catalogue.
    Returns dict(name, l1, l2, source, epoch). source: LIVE, CACHED, CACHED-STALE, ARCHIVED, APPROX."""
    try:
        n, l1, l2, src = fetch_tle_ex(norad, cache_dir, max_age_h, timeout)
        return dict(name=name or n, l1=l1, l2=l2, source=src, epoch=tle_epoch(l1))
    except TLEError as exc:
        if catalog is not None:
            found = catalog.tle_for(norad, name)
            if found:
                return found
        raise TLEError(f"no live TLE ({exc}) and no archived elements for NORAD {norad}") from exc


def _parse(text):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3 or not lines[1].startswith("1 ") or not lines[2].startswith("2 "):
        raise TLEError(f"unexpected TLE response: {text[:80]!r}")
    return lines[0], lines[1], lines[2]


def missing_package_message():
    return ("skyfield/sgp4 are not installed for the Python that runs this app. In the VS Code terminal run:  "
            f'"{sys.executable}" -m pip install -r requirements.txt   then restart. (Demo mode does not need them.)')


def _sky():
    try:
        from skyfield.api import load, wgs84, EarthSatellite
    except ImportError as exc:
        raise TLEError(missing_package_message()) from exc
    return load, wgs84, EarthSatellite


def _objects(name, l1, l2, station):
    load, wgs84, EarthSatellite = _sky()
    ts = load.timescale()
    return ts, EarthSatellite(l1, l2, name, ts), wgs84.latlon(station["lat"], station["lon"], station["alt_m"])


def predict_passes(name, l1, l2, station, start=None, hours=24, min_el=10):
    ts, sat, gs = _objects(name, l1, l2, station)
    start = start or dt.datetime.now(UTC)
    t, ev = sat.find_events(gs, ts.from_datetime(start), ts.from_datetime(start + dt.timedelta(hours=hours)),
                            altitude_degrees=min_el)
    out, cur = [], {}
    for ti, e in zip(t, ev):
        if e == 0:
            cur = {"name": name, "aos": ti.utc_datetime()}
        elif e == 1 and cur:
            cur["max_el"] = float((sat - gs).at(ti).altaz()[0].degrees)
        elif e == 2 and cur and "max_el" in cur:
            cur["los"] = ti.utc_datetime()
            out.append(cur)
            cur = {}
    return out


def sky_track(name, l1, l2, station, aos, los, n=60):
    """[(az, el)] from AOS to LOS."""
    ts, sat, gs = _objects(name, l1, l2, station)
    span = (los - aos) / n
    pts = []
    for k in range(n + 1):
        alt, az, _ = (sat - gs).at(ts.from_datetime(aos + span * k)).altaz()
        pts.append((az.degrees, alt.degrees))
    return pts


def azel_now(name, l1, l2, station, when=None):
    ts, sat, gs = _objects(name, l1, l2, station)
    alt, az, _ = (sat - gs).at(ts.from_datetime(when or dt.datetime.now(UTC))).altaz()
    return az.degrees, alt.degrees


def subpoint(name, l1, l2, when=None):
    load, wgs84, EarthSatellite = _sky()
    ts = load.timescale()
    sat = EarthSatellite(l1, l2, name, ts)
    sp = wgs84.subpoint(sat.at(ts.from_datetime(when or dt.datetime.now(UTC))))
    return sp.latitude.degrees, sp.longitude.degrees, sp.elevation.km
