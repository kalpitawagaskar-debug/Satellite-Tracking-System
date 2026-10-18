"""Run:  python -m unittest discover -s tests -v   (from the satellite_core folder)"""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import health
import routing
from dispatcher import Dispatcher, demo_network
from routing import Graph, Link


class ForceRng:
    """Returns scripted values for rng.random()."""
    def __init__(self, *vals): self.vals = list(vals)
    def random(self): return self.vals.pop(0)


def square():
    #   A --1-- B --1-- D        A-B-D = 2 (+ node costs), A-C-D longer, A-D direct longest
    return Graph([Link("A", "B", 299.792458), Link("B", "D", 299.792458),
                  Link("A", "C", 600), Link("C", "D", 600), Link("A", "D", 3000)])


class RoutingTests(unittest.TestCase):
    def test_fspl_known_value(self):
        self.assertAlmostEqual(routing.fspl_db(1000, 437), 145.25, places=1)

    def test_margin_sign(self):
        self.assertGreater(routing.link_margin_db(500, 437, 30, 2, 3, -116), 0)
        self.assertLess(routing.link_margin_db(50000, 437, 10, 0, 0, -110), 0)

    def test_k_best_paths_order_and_uniqueness(self):
        paths = square().k_best_paths("A", "D", 3)
        self.assertEqual(paths, [["A", "B", "D"], ["A", "C", "D"], ["A", "D"]])

    def test_down_link_excluded_and_no_path(self):
        g = Graph([Link("A", "B", 100, up=False), Link("B", "C", 100)])
        self.assertEqual(g.k_best_paths("A", "C"), [])

    def test_quality_changes_ranking(self):
        g = Graph([Link("A", "B", 300, 0.1), Link("B", "D", 300, 0.1),
                   Link("A", "C", 900, 1.0), Link("C", "D", 900, 1.0)])
        self.assertEqual(g.k_best_paths("A", "D", 1)[0], ["A", "C", "D"])

    def test_k_larger_than_available(self):
        self.assertEqual(len(square().k_best_paths("A", "D", 10)), 3)


class DispatchTests(unittest.TestCase):
    def test_failover_to_second_candidate(self):
        g = Graph([Link("A", "B", 300, 0.9), Link("B", "D", 300, 0.9),
                   Link("A", "C", 600, 0.9), Link("C", "D", 600, 0.9)])
        r = Dispatcher(g, ForceRng(0.99, 0.01)).dispatch("A", "D")    # first draw fails, second succeeds
        self.assertEqual(r.primary, ["A", "B", "D"])
        self.assertEqual([a.delivered for a in r.attempts], [False, True])
        self.assertEqual(r.final_path, ["A", "C", "D"])
        self.assertTrue(r.delivered)

    def test_all_attempts_fail(self):
        g = Graph([Link("A", "B", 300, 0.5), Link("B", "D", 300, 0.5), Link("A", "C", 600, 0.5),
                   Link("C", "D", 600, 0.5), Link("A", "D", 3000, 0.5)])
        r = Dispatcher(g, ForceRng(0.99, 0.99, 0.99)).dispatch("A", "D")
        self.assertFalse(r.delivered)
        self.assertEqual(len(r.attempts), 3)

    def test_unreachable(self):
        r = Dispatcher(Graph([Link("A", "B", 1)])).dispatch("A", "Z")
        self.assertEqual((r.primary, r.attempts, r.delivered), ([], [], False))

    def test_demo_network_runs_and_is_seeded(self):
        a = Dispatcher(demo_network(3), random.Random(5)).dispatch("GS", "SOMAIYAPOD")
        b = Dispatcher(demo_network(3), random.Random(5)).dispatch("GS", "SOMAIYAPOD")
        self.assertEqual(a.summary(), b.summary())
        self.assertTrue(a.candidates)


class HealthTests(unittest.TestCase):
    L = {"battery_pct": dict(warn=30, crit=15, bad_when="low"), "temp_c": dict(warn=55, crit=70, bad_when="high")}

    def test_all_ok(self):
        r = health.assess({"battery_pct": 80, "temp_c": 25}, self.L)
        self.assertEqual((r.status, r.score), ("OK", 100.0))

    def test_worst_metric_dominates(self):
        r = health.assess({"battery_pct": 80, "temp_c": 90}, self.L)
        self.assertEqual(r.status, "CRIT")
        self.assertLess(r.score, 50)

    def test_warn_band_interpolates(self):
        mid = health.metric_score(62.5, health.Limit(55, 70, "high"))
        self.assertAlmostEqual(mid, 45.0)

    def test_stale_and_no_data(self):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        r = health.assess({"battery_pct": 80}, self.L, last_rx=now - dt.timedelta(hours=2), now=now)
        self.assertEqual(r.status, "STALE")
        self.assertEqual(health.assess({}, self.L).status, "NO DATA")


if __name__ == "__main__":
    unittest.main()
