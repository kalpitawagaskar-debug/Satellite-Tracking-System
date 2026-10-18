"""Tests for CSV sniffing, OPS-SAT-AD import + detector, offline orbits and the improved outlier scan.
Run:  python -m unittest discover -s tests -v"""
import csv
import datetime as dt
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
import analytics
import detector
import ingest
import orbit_offline
from db import Database, OPS_FEATURES, UTC

try:
    import skyfield  # noqa: F401
    import sgp4  # noqa: F401
    HAVE_SKY = True
except ImportError:
    HAVE_SKY = False

DATA = os.path.join(ROOT, "data")
OPS_CSV = os.path.join(DATA, "dataset.csv")
CELESTRAK_CSV = os.path.join(DATA, "celestrak_satellite_dataset_3-April-2026.csv")
CATALOG_CSV = os.path.join(DATA, "satellite_catalog.csv")


def temp_db():
    d = tempfile.mkdtemp()
    db = Database(os.path.join(d, "t.db"))
    db.init_schema()
    return db, d


def write_fake_ops(path, n=300, seed=3):
    """Tiny OPS-SAT-AD-shaped file: anomalies have larger variance and more peaks."""
    import random
    rnd = random.Random(seed)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["segment", "anomaly", "train", "channel", "sampling"] + OPS_FEATURES)
        for i in range(n):
            an = 1 if rnd.random() < 0.25 else 0
            feats = [rnd.uniform(50, 300), rnd.uniform(50, 300), rnd.gauss(0, 1), rnd.uniform(0.5, 1) * (6 if an else 1),
                     rnd.uniform(0.5, 1) * (3 if an else 1), rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.randint(1, 5) + 6 * an,
                     rnd.randint(1, 5), rnd.randint(1, 5), rnd.randint(1, 5), rnd.randint(1, 5), rnd.random(), rnd.random(),
                     rnd.random(), rnd.random(), rnd.random(), rnd.random()]
            w.writerow([i, an, 1 if i % 4 else 0, f"CH{i % 3}", 1] + feats)


class MissingDependencyTests(unittest.TestCase):
    def test_missing_skyfield_gives_actionable_one_line_error(self):
        import passes
        from unittest import mock
        from workers import UserFacingError
        with mock.patch.dict(sys.modules, {"skyfield": None, "skyfield.api": None}):
            with self.assertRaises(passes.TLEError) as cm:
                passes._sky()
        self.assertIsInstance(cm.exception, UserFacingError)
        self.assertIn("-m pip install -r requirements.txt", str(cm.exception))


class SniffTests(unittest.TestCase):
    def test_each_file_type_recognised(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "frames.csv")
        ingest.write_synthetic_csv(p, n=5)
        self.assertEqual(ingest.sniff_csv(p)[0], "frames")
        p2 = os.path.join(d, "ops.csv")
        write_fake_ops(p2, 30)
        self.assertEqual(ingest.sniff_csv(p2)[0], "ops_features")
        p3 = os.path.join(d, "x.csv")
        with open(p3, "w") as f:
            f.write("foo,bar\n1,2\n")
        self.assertEqual(ingest.sniff_csv(p3)[0], "unknown")

    @unittest.skipUnless(os.path.exists(OPS_CSV), "repo data files not present")
    def test_repo_files_recognised(self):
        self.assertEqual(ingest.sniff_csv(OPS_CSV)[0], "ops_features")
        self.assertEqual(ingest.sniff_csv(CELESTRAK_CSV)[0], "celestrak_elements")
        self.assertEqual(ingest.sniff_csv(CATALOG_CSV)[0], "catalog")


class OpsImportTests(unittest.TestCase):
    def test_import_idempotent_and_bad_rows(self):
        db, d = temp_db()
        p = os.path.join(d, "ops.csv")
        write_fake_ops(p, 100)
        with open(p, "a") as f:
            f.write("999,2,1,CHX,1," + ",".join(["1"] * 18) + "\n")      # anomaly flag 2 = invalid
        s1 = ingest.load_ops_features(db, p, "T")
        self.assertEqual((s1["read"], s1["inserted"], s1["bad"]), (101, 100, 1))
        self.assertEqual(ingest.load_ops_features(db, p, "T")["inserted"], 0)
        self.assertEqual(db.ops_count("T"), 100)

    def test_missing_columns_raises(self):
        db, d = temp_db()
        p = os.path.join(d, "bad.csv")
        with open(p, "w") as f:
            f.write("segment,anomaly,train,channel,sampling,duration\n1,0,1,A,1,5\n")
        with self.assertRaises(ingest.IngestError):
            ingest.load_ops_features(db, p)


class DetectorTests(unittest.TestCase):
    def test_learns_synthetic_signal_and_reports_structure(self):
        db, d = temp_db()
        p = os.path.join(d, "ops.csv")
        write_fake_ops(p, 600)
        ingest.load_ops_features(db, p, "T")
        r = detector.evaluate_rows(db.ops_segments("T"))
        m = r["model"]
        self.assertEqual(m["tp"] + m["fp"] + m["fn"] + m["tn"], r["n_test"])
        self.assertGreater(m["f1"], 0.8)
        self.assertIn("without_size_features", r)
        self.assertLessEqual(len(r["top_features"]), 5)

    def test_refuses_without_data_or_single_class(self):
        with self.assertRaises(ValueError):
            detector.evaluate_rows([])
        with self.assertRaises(ValueError):
            detector.LogisticDetector().fit([[1.0], [2.0]], [0, 0])

    def test_confusion_arithmetic(self):
        c = detector.confusion([1, 1, 0, 0, 1], [1, 0, 0, 1, 1])
        self.assertEqual((c["tp"], c["fp"], c["fn"], c["tn"]), (2, 1, 1, 1))
        self.assertAlmostEqual(c["precision"], 2 / 3)
        self.assertAlmostEqual(c["recall"], 2 / 3)

    @unittest.skipUnless(os.path.exists(OPS_CSV), "repo data files not present")
    def test_real_dataset_numbers(self):
        """Pins what was actually measured on the supplied OPS-SAT-AD file."""
        db, _ = temp_db()
        st = ingest.load_ops_features(db, OPS_CSV, "OPSSAT-AD")
        self.assertEqual((st["read"], st["inserted"], st["bad"]), (2123, 2123, 0))
        r = detector.evaluate_rows(db.ops_segments("OPSSAT-AD"))
        self.assertEqual((r["n_train"], r["n_test"]), (1594, 529))
        self.assertGreater(r["model"]["f1"], 0.85)
        self.assertGreater(r["model"]["f1"], r["unsupervised"]["f1"] + 0.4)     # supervised beats unsupervised clearly
        self.assertAlmostEqual(r["always_nominal_accuracy"], 0.786, places=2)


class AnalyticsTests(unittest.TestCase):
    def test_orbit_periodic_signal_no_false_alarms_but_spike_found(self):
        """Period 191 samples = one 95.5-min orbit at 30 s cadence. The scan assumes the signal moves
        slowly compared with its 21-sample window; much faster oscillations would false-alarm."""
        n = 400
        vals = [50 + 20 * math.sin(2 * math.pi * i / 191) + (0.3 if i % 2 else -0.3) for i in range(n)]
        vals[200] += 40
        rows = [(f"2026-01-01T{i // 3600:02d}:{i % 3600 // 60:02d}:{i % 60:02d}Z", v) for i, v in enumerate(vals)]
        df = analytics.flag_anomalies(analytics.series_frame(rows))
        flagged = [i for i, v in enumerate(df["anomaly"]) if v]
        self.assertEqual(flagged, [200])


@unittest.skipUnless(HAVE_SKY, "skyfield/sgp4 not installed")
class OfflineOrbitTests(unittest.TestCase):
    def test_make_tle_roundtrip_matches_inputs(self):
        import passes
        ep = dt.datetime(2026, 4, 2, 22, 22, 53, tzinfo=UTC)
        n, l1, l2 = orbit_offline.make_tle("T", 25544, ep, 51.64, 100.0, 0.0005, 80.0, 10.0, 15.5)
        self.assertEqual(len(l1), 69)
        self.assertEqual(len(l2), 69)
        self.assertLess(abs((passes.tle_epoch(l1) - ep).total_seconds()), 1.0)
        self.assertAlmostEqual(float(l2[8:16]), 51.64, places=3)          # inclination field
        self.assertAlmostEqual(float(l2[52:63]), 15.5, places=4)          # mean motion field

    @unittest.skipUnless(os.path.exists(CELESTRAK_CSV), "repo data files not present")
    def test_archived_orbit_is_geometrically_consistent(self):
        import passes
        cat = orbit_offline.ElementsCatalog(CELESTRAK_CSV, CATALOG_CSV)
        o = cat.tle_for(27848)                       # CUBESAT XI-IV (CO-57), in both files
        self.assertEqual(o["source"], "ARCHIVED")
        when = o["epoch"] + dt.timedelta(minutes=30)
        lats, alts = [], []
        for k in range(0, 100, 2):
            la, lo, al = passes.subpoint(o["name"], o["l1"], o["l2"], when + dt.timedelta(minutes=k))
            lats.append(abs(la)); alts.append(al)
        self.assertGreater(max(lats), 75)                                  # polar orbit (inclination 98.7 deg)
        self.assertTrue(780 < sum(alts) / len(alts) < 880)                # catalogue says about 815-836 km

    @unittest.skipUnless(os.path.exists(CELESTRAK_CSV), "repo data files not present")
    def test_unmatched_name_falls_back_to_approx_and_unknown_is_none(self):
        cat = orbit_offline.ElementsCatalog(CELESTRAK_CSV, CATALOG_CSV)
        names = cat.names()
        unmatched = [n for n, nm in names.items() if nm not in cat._by_name]
        self.assertTrue(unmatched)
        self.assertEqual(cat.tle_for(unmatched[0])["source"], "APPROX")
        self.assertIsNone(cat.tle_for(1))


if __name__ == "__main__":
    unittest.main()
