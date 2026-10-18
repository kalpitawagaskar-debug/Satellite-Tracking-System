"""GUI-free dispatcher: rank routes, try them in order, record every attempt.
Result fields (primary / candidates / attempts) mirror what a route panel normally shows.
The random generator is injected so tests are deterministic.
"""
import random
from dataclasses import dataclass, field


@dataclass
class Attempt:
    path: list
    delivered: bool
    latency_ms: float
    reason: str = ""


@dataclass
class DispatchResult:
    src: str
    dst: str
    primary: list = field(default_factory=list)
    candidates: list = field(default_factory=list)      # [(path, cost, p_deliver)]
    attempts: list = field(default_factory=list)
    delivered: bool = False

    @property
    def final_path(self):
        return next((a.path for a in self.attempts if a.delivered), None)

    def summary(self):
        lines = [f"{self.src} -> {self.dst}  primary: {' > '.join(self.primary) or 'NONE'}"]
        for i, a in enumerate(self.attempts, 1):
            lines.append(f"  attempt {i}: {' > '.join(a.path)}  {'OK' if a.delivered else 'FAIL'}  "
                         f"{a.latency_ms:.1f} ms  {a.reason}".rstrip())
        lines.append("  DELIVERED" if self.delivered else "  NOT DELIVERED")
        return lines


class Dispatcher:
    def __init__(self, graph, rng=None, k=3, max_attempts=3):
        self.graph, self.rng, self.k, self.max_attempts = graph, rng or random.Random(), k, max_attempts

    def dispatch(self, src, dst):
        res = DispatchResult(src, dst)
        paths = self.graph.k_best_paths(src, dst, self.k)
        res.candidates = [(p, round(self.graph.path_cost(p), 2), round(self.graph.path_delivery(p), 3)) for p in paths]
        if not paths:
            return res
        res.primary = paths[0]
        for p in paths[:self.max_attempts]:
            ok = self.rng.random() < self.graph.path_delivery(p)
            res.attempts.append(Attempt(p, ok, self.graph.path_latency_ms(p),
                                        "" if ok else "no ACK, trying next candidate"))
            if ok:
                res.delivered = True
                break
        return res


def demo_network(seed=1, freq_mhz=437.0):
    """Illustrative links only: distances are made up, not from real orbits."""
    from routing import Graph, Link, link_margin_db, delivery_probability
    rnd = random.Random(seed)
    spec = [("GS", "SOMAIYASAT", 1800, 0.0), ("GS", "SOMAIYAPOD", 2600, 0.0),
            ("SOMAIYASAT", "SOMAIYAPOD", 900, 0.0), ("GS", "RELAY-X", 3200, 0.0),
            ("RELAY-X", "SOMAIYAPOD", 1500, 0.0)]
    links = []
    for a, b, d, _ in spec:
        d *= rnd.uniform(0.9, 1.1)
        m = link_margin_db(d, freq_mhz, tx_dbm=30, tx_gain_dbi=2, rx_gain_dbi=3, rx_sens_dbm=-116) + rnd.uniform(-4, 4)
        links.append(Link(a, b, d, delivery_probability(m)))
    return Graph(links)
