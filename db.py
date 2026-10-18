"""SQLite access layer. One connection per thread (sqlite3 objects must not be
shared across threads), WAL mode so the UI can read while a worker writes.
Use a real file path, not ':memory:' (each thread would get a different DB).
"""
import sqlite3
import threading
import datetime as dt
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")
UTC = dt.timezone.utc

OPS_FEATURES = ["duration", "len", "mean", "var", "std", "kurtosis", "skew", "n_peaks",
                "smooth10_n_peaks", "smooth20_n_peaks", "diff_peaks", "diff2_peaks", "diff_var",
                "diff2_var", "gaps_squared", "len_weighted", "var_div_duration", "var_div_len"]


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local, self._conns, self._lock = threading.local(), [], threading.Lock()

    @property
    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.c = c
            with self._lock:
                self._conns.append(c)
        return c

    def init_schema(self):
        with self.conn:
            self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    def close_all(self):
        with self._lock:
            for c in self._conns:
                try:
                    c.close()
                except sqlite3.ProgrammingError:
                    pass  # opened in another thread; closes when that thread ends
            self._conns.clear()

    # ---- satellites / frames
    def upsert_satellite(self, norad, name):
        with self.conn:
            self.conn.execute("INSERT INTO satellites(norad_id,name) VALUES(?,?) "
                              "ON CONFLICT(norad_id) DO UPDATE SET name=excluded.name", (norad, name))

    def insert_frames(self, rows):
        """rows: (norad, rx_time_iso, frame_hex, observer, observation_id). Returns rows newly inserted."""
        c = self.conn
        before = c.total_changes
        with c:
            c.executemany("INSERT OR IGNORE INTO frames(norad_id,rx_time,frame_hex,observer,observation_id) "
                          "VALUES(?,?,?,?,?)", rows)
        return c.total_changes - before

    def frame_count(self, norad=None):
        q, a = "SELECT COUNT(*) FROM frames", ()
        if norad is not None:
            q, a = q + " WHERE norad_id=?", (norad,)
        return self.conn.execute(q, a).fetchone()[0]

    def clear_telemetry(self, norad):
        """Delete stored frames and housekeeping of one satellite (used to refresh DEMO data only)."""
        with self.conn:
            self.conn.execute("DELETE FROM housekeeping WHERE norad_id=?", (norad,))
            self.conn.execute("DELETE FROM frames WHERE norad_id=?", (norad,))

    def last_frame_time(self, norad):
        r = self.conn.execute("SELECT MAX(rx_time) FROM frames WHERE norad_id=?", (norad,)).fetchone()[0]
        return parse_iso(r) if r else None

    # ---- housekeeping
    def add_housekeeping(self, rows):
        """rows: (norad, ts_iso, metric, value)."""
        c = self.conn
        before = c.total_changes
        with c:
            c.executemany("INSERT OR IGNORE INTO housekeeping(norad_id,ts,metric,value) VALUES(?,?,?,?)", rows)
        return c.total_changes - before

    def metric_series(self, norad, metric, limit=2000):
        rows = self.conn.execute("SELECT ts,value FROM housekeeping WHERE norad_id=? AND metric=? "
                                 "ORDER BY ts DESC LIMIT ?", (norad, metric, limit)).fetchall()
        return [(r["ts"], r["value"]) for r in reversed(rows)]

    def latest_values(self, norad):
        rows = self.conn.execute(
            "SELECT h.metric, h.value FROM housekeeping h JOIN ("
            " SELECT metric, MAX(ts) mts FROM housekeeping WHERE norad_id=? GROUP BY metric) m "
            "ON h.metric=m.metric AND h.ts=m.mts WHERE h.norad_id=?", (norad, norad)).fetchall()
        return {r["metric"]: r["value"] for r in rows}

    # ---- passes
    def save_passes(self, norad, passes):
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO passes(norad_id,aos,los,max_el) VALUES(?,?,?,?)",
                [(norad, iso(p["aos"]), iso(p["los"]), float(p["max_el"])) for p in passes])

    def clear_future_passes(self, norad, now=None):
        """Drop stored passes that have not finished yet, so a recompute never leaves duplicates."""
        with self.conn:
            self.conn.execute("DELETE FROM passes WHERE norad_id=? AND los>?",
                              (norad, iso(now or dt.datetime.now(UTC))))

    def upcoming_passes(self, norad, now=None, limit=8):
        now = now or dt.datetime.now(UTC)
        rows = self.conn.execute("SELECT aos,los,max_el FROM passes WHERE norad_id=? AND los>? "
                                 "ORDER BY aos LIMIT ?", (norad, iso(now), limit)).fetchall()
        return [{"aos": parse_iso(r["aos"]), "los": parse_iso(r["los"]), "max_el": r["max_el"]} for r in rows]

    # ---- events
    def log_event(self, level, message):
        with self.conn:
            self.conn.execute("INSERT INTO events(ts,level,message) VALUES(?,?,?)",
                              (iso(dt.datetime.now(UTC)), level.upper(), message))

    def recent_events(self, n=50):
        rows = self.conn.execute("SELECT ts,level,message FROM events ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [(r["ts"], r["level"], r["message"]) for r in reversed(rows)]

    # ---- OPS-SAT-AD segments
    def save_ops_segments(self, dataset, rows):
        """rows: dicts with segment, channel, sampling, train, anomaly + every OPS_FEATURES key."""
        cols = ["dataset", "segment", "channel", "sampling", "train", "anomaly"] + OPS_FEATURES
        sql = "INSERT OR IGNORE INTO ops_segments(%s) VALUES(%s)" % (",".join(f'"{c}"' for c in cols), ",".join("?" * len(cols)))
        c = self.conn
        before = c.total_changes
        with c:
            c.executemany(sql, [(dataset, r["segment"], r["channel"], r["sampling"], r["train"], r["anomaly"],
                                 *[r[f] for f in OPS_FEATURES]) for r in rows])
        return c.total_changes - before

    def ops_count(self, dataset):
        return self.conn.execute("SELECT COUNT(*) FROM ops_segments WHERE dataset=?", (dataset,)).fetchone()[0]

    def ops_segments(self, dataset):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM ops_segments WHERE dataset=? ORDER BY segment", (dataset,)).fetchall()]
