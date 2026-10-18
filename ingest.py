"""CSV -> SQLite loader for SatNOGS-style frame exports, plus a synthetic data generator.

IMPORTANT (verified from SatNOGS forum threads): exported frames are RAW HEX. Turning them
into battery/temperature values needs a decoder written for that specific satellite.
The exact CSV header names were NOT verified, so columns are auto-detected from aliases;
if detection fails you get the real header list and can pass mapping={...} yourself.
"""
import csv
import math
import random
import re
import struct
import datetime as dt
from db import iso, UTC, OPS_FEATURES
from workers import UserFacingError

ALIASES = {
    "rx_time": ["timestamp", "time", "rx_time", "received", "date", "datetime"],
    "frame_hex": ["frame", "hex", "data", "payload", "raw", "frame_hex"],
    "observer": ["observer", "station", "ground_station", "callsign"],
    "observation_id": ["observation_id", "observation", "obs_id", "observation id"],
}
HEX_RE = re.compile(r"^[0-9A-F]+$")


class IngestError(UserFacingError):
    pass


def detect_columns(header):
    low = {h.strip().lower(): h for h in header}
    found = {k: next((low[a] for a in al if a in low), None) for k, al in ALIASES.items()}
    missing = [k for k in ("rx_time", "frame_hex") if not found[k]]
    if missing:
        raise IngestError(f"Could not find column(s) {missing}. File header is: {list(header)}. "
                          f"Pass mapping={{'rx_time': '<col>', 'frame_hex': '<col>'}}.")
    return found


def normalise_hex(s):
    h = re.sub(r"[\s:]", "", str(s)).upper()
    if not h or len(h) % 2 or not HEX_RE.match(h):
        raise ValueError(f"not valid hex: {str(s)[:30]!r}")
    return h


def parse_timestamp(s):
    d = dt.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    return iso(d if d.tzinfo else d.replace(tzinfo=UTC))


def load_csv(db, path, norad_id, name=None, mapping=None, decoder=None, batch=1000, progress=None):
    """Load frames. decoder(hex)->{metric: value} optionally fills the housekeeping table.
    Returns dict(read, inserted, bad, housekeeping)."""
    db.upsert_satellite(norad_id, name or f"NORAD {norad_id}")
    stats = dict(read=0, inserted=0, bad=0, housekeeping=0)
    frames, hk = [], []

    def flush():
        stats["inserted"] += db.insert_frames(frames)
        stats["housekeeping"] += db.add_housekeeping(hk)
        frames.clear()
        hk.clear()

    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = {**detect_columns(rd.fieldnames or []), **(mapping or {})}
        for row in rd:
            stats["read"] += 1
            try:
                ts, hx = parse_timestamp(row[cols["rx_time"]]), normalise_hex(row[cols["frame_hex"]])
                obs = row.get(cols["observation_id"]) if cols.get("observation_id") else None
                frames.append((norad_id, ts, hx, row.get(cols["observer"]) if cols.get("observer") else None,
                               int(obs) if obs and str(obs).isdigit() else None))
                if decoder:
                    hk.extend((norad_id, ts, m, float(v)) for m, v in (decoder(hx) or {}).items())
            except (ValueError, KeyError, struct.error):
                stats["bad"] += 1
            if len(frames) >= batch:
                flush()
                if progress:
                    progress(stats["read"])
    flush()
    return stats


# ---------------- synthetic demo data (NOT real telemetry) ----------------
FMT = ">BBBHbB"   # magic, battery %, temp+40, bus mV, rssi dBm, solar deci-watts


def demo_decoder(hx):
    raw = bytes.fromhex(hx)
    if len(raw) != struct.calcsize(FMT) or raw[0] != 0xAA:
        return None
    _, bat, t40, mv, rssi, sol = struct.unpack(FMT, raw)
    return {"battery_pct": bat, "temp_c": t40 - 40, "bus_v": mv / 1000, "rssi_dbm": rssi, "solar_w": sol / 10}


def write_synthetic_csv(path, n=720, seed=1, end=None):
    """Writes a SatNOGS-like CSV with fake frames, orbit-periodic trends and injected faults."""
    rnd, end = random.Random(seed), end or dt.datetime.now(UTC)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "frame", "observer", "observation_id"])
        for i in range(n):
            t = end - dt.timedelta(seconds=30 * (n - i))
            ph = 2 * math.pi * (30 * i) / (95.5 * 60)
            bat = 78 + 12 * math.sin(ph) + rnd.uniform(-1, 1)
            temp = 28 + 9 * math.sin(ph + 1) + rnd.uniform(-1, 1) + (35 if i in (400, 401) else 0)
            rssi = -112 + rnd.uniform(-6, 6) - (25 if 560 <= i < 566 else 0)
            sol = max(0.0, 2.4 * math.sin(ph)) + rnd.uniform(0, 0.2)
            frame = struct.pack(FMT, 0xAA, int(bat), int(temp + 40), int(3900 + 150 * math.sin(ph)),
                                max(-128, int(rssi)), int(sol * 10))
            w.writerow([t.strftime("%Y-%m-%dT%H:%M:%SZ"), frame.hex().upper(), "DEMO-GS", 1000 + i // 40])


# ---------------- file-type detection and the OPS-SAT-AD feature importer ----------------
OPS_KEYS = ("segment", "anomaly", "train", "channel")


def sniff_csv(path):
    """Look at the header only. Returns (kind, header) where kind is one of
    'frames', 'ops_features', 'celestrak_elements', 'catalog', 'unknown'."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    low = {h.strip().lower() for h in header}
    if set(OPS_KEYS) <= low and len(low & set(OPS_FEATURES)) >= 10:
        return "ops_features", header
    if {"name", "epoch", "inclination_deg", "raan_deg", "mean_motion_rev_per_day"} <= low:
        return "celestrak_elements", header
    if {"satellite_id", "satellite_name"} <= low:
        return "catalog", header
    try:
        detect_columns(header)
        return "frames", header
    except IngestError:
        return "unknown", header


def load_ops_features(db, path, dataset="OPSSAT-AD", batch=500, progress=None):
    """Import the OPS-SAT-AD segment/feature table (dataset.csv). Returns dict(read, inserted, bad)."""
    stats = dict(read=0, inserted=0, bad=0)
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        missing = [c for c in (*OPS_KEYS, *OPS_FEATURES) if c not in (rd.fieldnames or [])]
        if missing:
            raise IngestError(f"OPS-SAT-AD file is missing column(s) {missing}")
        for row in rd:
            stats["read"] += 1
            try:
                rec = {"segment": int(float(row["segment"])), "channel": row["channel"].strip(),
                       "sampling": float(row["sampling"]), "train": int(float(row["train"])),
                       "anomaly": int(float(row["anomaly"]))}
                if rec["train"] not in (0, 1) or rec["anomaly"] not in (0, 1) or not rec["channel"]:
                    raise ValueError("bad flag")
                for k in OPS_FEATURES:
                    v = float(row[k])
                    if not math.isfinite(v):
                        raise ValueError("non-finite feature")
                    rec[k] = v
                rows.append(rec)
            except (ValueError, KeyError, TypeError):
                stats["bad"] += 1
            if len(rows) >= batch:
                stats["inserted"] += db.save_ops_segments(dataset, rows)
                rows.clear()
                if progress:
                    progress(stats["read"])
    stats["inserted"] += db.save_ops_segments(dataset, rows)
    return stats
