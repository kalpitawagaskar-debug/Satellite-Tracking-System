"""GUI-free health engine: turns latest housekeeping values into one 0-100 score.

The limits in config.THRESHOLDS are EXAMPLES, not validated for any PocketQube.
Anything shown to users must stay labelled SIMULATED / EXAMPLE LIMITS.
"""
from dataclasses import dataclass, field
import datetime as dt


@dataclass(frozen=True)
class Limit:
    warn: float
    crit: float
    bad_when: str = "high"          # "high": big values are bad; "low": small values are bad


def metric_status(value, lim):
    if lim.bad_when == "high":
        return "CRIT" if value >= lim.crit else "WARN" if value >= lim.warn else "OK"
    return "CRIT" if value <= lim.crit else "WARN" if value <= lim.warn else "OK"


def metric_score(value, lim):
    """OK = 100. Inside the WARN band the score falls linearly from 70 (at warn) to 20 (at crit).
    Beyond crit = 10."""
    st = metric_status(value, lim)
    if st == "OK":
        return 100.0
    if st == "CRIT":
        return 10.0
    span = abs(lim.crit - lim.warn) or 1.0
    return 70.0 - 50.0 * min(1.0, abs(value - lim.warn) / span)


@dataclass
class HealthReport:
    score: float
    status: str                      # OK / WARN / CRIT / STALE / NO DATA
    per_metric: dict = field(default_factory=dict)   # metric -> (value, status, score)


def assess(values, limits, last_rx=None, now=None, stale_after_min=30):
    """values: {metric: value}; limits: {metric: Limit or dict(warn,crit,bad_when)}.
    Score = 0.6 * worst metric + 0.4 * mean, so one failing subsystem cannot hide in an average."""
    lims = {m: l if isinstance(l, Limit) else Limit(**l) for m, l in limits.items()}
    per = {m: (v, metric_status(v, lims[m]), metric_score(v, lims[m])) for m, v in values.items() if m in lims}
    if not per:
        return HealthReport(0.0, "NO DATA", {})
    scores = [s for _, _, s in per.values()]
    score = 0.6 * min(scores) + 0.4 * sum(scores) / len(scores)
    status = "CRIT" if any(st == "CRIT" for _, st, _ in per.values()) else \
             "WARN" if any(st == "WARN" for _, st, _ in per.values()) else "OK"
    now = now or dt.datetime.now(dt.timezone.utc)
    if last_rx and (now - last_rx).total_seconds() > stale_after_min * 60:
        status = "STALE"
    return HealthReport(round(score, 1), status, per)
