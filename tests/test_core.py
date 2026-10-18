"""Run:  python -m unittest discover -s tests -v     (from the satellite_core folder)"""
import csv
import logging
import datetime as dt
import math
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analytics
import ingest
import workers
from db import Database, UTC

try:
    import skyfield  # noqa: F401
    from sgp4.api import Satrec, WGS72
    from sgp4.exporter import export_tle
    HAVE_SKY = True
except ImportError:
    HAVE_SKY = False


def temp_db():
    d = tempfile.mkdtemp()
    db = Database(os.path.join(d, "t.db"))
    db.init_schema()
    return db, d


class DbIngestTests(unittest.TestCase):
    def test_roundtrip_and_dedupe(self):
        db, d = temp_db()
        p = os.path.join(d, "f.csv")
        ingest.write_synthetic_csv(p, n=120)
        s1 = ingest.load_csv(db, p, 99999, decoder=ingest.demo_decoder)
        self.assertEqual((s1["read"], s1["inserted"], s1["bad"]), (120, 120, 0))
        self.assertEqual(s1["housekeeping"], 120 * 5)
        s2 = ingest.load_csv(db, p, 99999, decoder=ingest.demo_decoder)   # same file again
        self.assertEqual(s2["inserted"], 0)
        self.assertEqual(db.frame_count(99999), 120)
        self.assertIn("battery_pct", db.latest_values(99999))
        self.assertEqual(len(db.metric_series(99999, "temp_c")), 120)

    def test_bad_rows_counted_not_fatal(self):
        db, d = temp_db()
        p = os.path.join(d, "bad.csv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Timestamp", "Frame"])
            w.writerow(["2026-01-01T00:00:00Z", "AA BB CC"])
            w.writerow(["not-a-date", "AABB"])
            w.writerow(["2026-01-01T00:00:01Z", "XYZ"])
            w.writerow(["2026-01-01T00:00:02Z", "ABC"])      # odd length
        s = ingest.load_csv(db, p, 1)
        self.assertEqual((s["inserted"], s["bad"]), (1, 3))

    def test_unknown_header_gives_helpful_error(self):
        db, d = temp_db()
        p = os.path.join(d, "x.csv")
        with open(p, "w") as f:
            f.write("foo,bar\n1,2\n")
        with self.assertRaises(ingest.IngestError) as cm:
            ingest.load_csv(db, p, 1)
        self.assertIn("foo", str(cm.exception))

    def test_threads_get_own_connection(self):
        db, _ = temp_db()
        db.upsert_satellite(1, "A")
        out = []
        t = threading.Thread(target=lambda: out.append(db.frame_count()))
        t.start(); t.join()
        self.assertEqual(out, [0])


class AnalyticsTests(unittest.TestCase):
    def test_spike_flagged(self):
        db, d = temp_db()
        p = os.path.join(d, "f.csv")
        ingest.write_synthetic_csv(p, n=720)
        ingest.load_csv(db, p, 99999, decoder=ingest.demo_decoder)
        df = analytics.flag_anomalies(analytics.series_frame(db.metric_series(99999, "temp_c")), window=20, z=3.5)
        self.assertGreaterEqual(int(df["anomaly"].sum()), 1)
        self.assertTrue(df["anomaly"].iloc[400:403].any())    # injected fault at index 400-401

    def test_limits(self):
        df = analytics.series_frame([("2026-01-01T00:00:0%dZ" % i, v) for i, v in enumerate([20, 56, 71, 30])])
        self.assertEqual(analytics.limit_violations(df, 55, 70, "high"), dict(warn=1, crit=1))


class FakeRoot:
    def __init__(self): self.jobs = []
    def after(self, ms, fn=None): self.jobs.append(fn); return len(self.jobs)
    def after_cancel(self, i): pass


class WorkerTests(unittest.TestCase):
    def test_result_and_error_delivered_on_pump(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        w = workers.TkWorker(FakeRoot())
        got = []
        w.submit(lambda: 41 + 1, on_done=got.append)
        w.submit(lambda: 1 / 0, on_error=lambda e: got.append(type(e).__name__))
        w._pool.shutdown(wait=True)
        w.pump()
        self.assertEqual(sorted(map(str, got)), ["42", "ZeroDivisionError"])

    def test_callback_runs_in_pumping_thread(self):
        w = workers.TkWorker(FakeRoot())
        names = []
        w.submit(lambda: 1, on_done=lambda _: names.append(threading.current_thread().name))
        w._pool.shutdown(wait=True)
        w.pump()
        self.assertEqual(names, [threading.current_thread().name])


@unittest.skipUnless(HAVE_SKY, "skyfield/sgp4 not installed")
class PassTests(unittest.TestCase):
    def test_predict_with_generated_tle(self):
        import passes
        now = dt.datetime.now(UTC)
        epoch = (now - dt.datetime(1949, 12, 31, tzinfo=UTC)).total_seconds() / 86400
        s = Satrec()
        s.sgp4init(WGS72, "i", 99999, epoch, 1e-5, 0.0, 0.0, 0.001, 0.0, math.radians(97.5), 0.0,
                   2 * math.pi / 95.5, 0.0)
        l1, l2 = export_tle(s)
        st = dict(lat=19.08, lon=72.90, alt_m=10)
        ps = passes.predict_passes("TEST", l1, l2, st, start=now, hours=48, min_el=5)
        self.assertGreater(len(ps), 3)
        self.assertTrue(all(p["los"] > p["aos"] and 5 <= p["max_el"] <= 90 for p in ps))
        track = passes.sky_track("TEST", l1, l2, st, ps[0]["aos"], ps[0]["los"], n=20)
        self.assertEqual(len(track), 21)
        lat, lon, alt = passes.subpoint("TEST", l1, l2, now)
        self.assertTrue(-90 <= lat <= 90 and -180 <= lon <= 180 and 300 < alt < 900)


if __name__ == "__main__":
    unittest.main()
