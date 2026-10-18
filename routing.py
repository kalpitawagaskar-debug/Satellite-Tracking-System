"""GUI-free routing engine: link budget, link-cost graph, k best paths (Yen's algorithm).

This is classical shortest-path routing, NOT machine learning. Do not describe it as AI in
your report; describe it as autonomous, link-quality-aware routing (simulated).
"""
import heapq
import math
from dataclasses import dataclass

C_KM_S = 299_792.458


def fspl_db(distance_km, freq_mhz):
    """Free-space path loss in dB (distance in km, frequency in MHz)."""
    return 20 * math.log10(distance_km) + 20 * math.log10(freq_mhz) + 32.44


def link_margin_db(distance_km, freq_mhz, tx_dbm, tx_gain_dbi, rx_gain_dbi, rx_sens_dbm):
    """Received power minus receiver sensitivity. Negative margin = link does not close."""
    return tx_dbm + tx_gain_dbi + rx_gain_dbi - fspl_db(distance_km, freq_mhz) - rx_sens_dbm


def delivery_probability(margin_db, full_at=10.0):
    """Toy mapping margin -> probability (0 at <=0 dB, 1 at >= full_at dB). Replace with a
    measured packet-loss curve if you have one."""
    return max(0.0, min(1.0, margin_db / full_at))


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    distance_km: float
    p_deliver: float = 1.0
    up: bool = True

    @property
    def latency_ms(self):
        return self.distance_km / C_KM_S * 1000

    @property
    def cost(self):
        """Lower is better: propagation delay plus a penalty that grows as quality drops."""
        return self.latency_ms + 50.0 * (1.0 - self.p_deliver) + 1.0


class Graph:
    def __init__(self, links):
        self.links = {}
        for l in links:
            self.links[frozenset((l.a, l.b))] = l
        self.nodes = {n for l in links for n in (l.a, l.b)}

    def neighbours(self, n, banned_nodes=(), banned_edges=()):
        for l in self.links.values():
            if not l.up or n not in (l.a, l.b):
                continue
            m = l.b if l.a == n else l.a
            if m in banned_nodes or frozenset((n, m)) in banned_edges:
                continue
            yield m, l

    def path_cost(self, path):
        return sum(self.links[frozenset(p)].cost for p in zip(path, path[1:]))

    def path_delivery(self, path):
        pr = 1.0
        for p in zip(path, path[1:]):
            pr *= self.links[frozenset(p)].p_deliver
        return pr

    def path_latency_ms(self, path):
        return sum(self.links[frozenset(p)].latency_ms for p in zip(path, path[1:]))

    def shortest(self, src, dst, banned_nodes=(), banned_edges=()):
        dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == dst:
                out = [dst]
                while out[-1] != src:
                    out.append(prev[out[-1]])
                return out[::-1]
            if d > dist.get(n, math.inf):
                continue
            for m, l in self.neighbours(n, banned_nodes, banned_edges):
                nd = d + l.cost
                if nd < dist.get(m, math.inf):
                    dist[m], prev[m] = nd, n
                    heapq.heappush(pq, (nd, m))
        return None

    def k_best_paths(self, src, dst, k=3):
        """Yen's algorithm: the k cheapest loop-free paths, cheapest first."""
        first = self.shortest(src, dst)
        if not first:
            return []
        found, cand = [first], []
        for _ in range(1, k):
            last = found[-1]
            for i in range(len(last) - 1):
                root = last[:i + 1]
                banned_e = {frozenset((p[i], p[i + 1])) for p in found if p[:i + 1] == root and len(p) > i + 1}
                spur = self.shortest(root[-1], dst, banned_nodes=set(root[:-1]), banned_edges=banned_e)
                if spur:
                    total = root[:-1] + spur
                    item = (self.path_cost(total), total)
                    if total not in found and item not in cand:
                        cand.append(item)
            if not cand:
                break
            cand.sort()
            found.append(cand.pop(0)[1])
        return found
