"""pandas helpers: summary stats, rolling z-score anomalies, threshold checks, pass stats."""
import numpy as np
import pandas as pd


def series_frame(rows):
    """rows: [(iso_ts, value)] -> DataFrame indexed by UTC time with a 'value' column."""
    df = pd.DataFrame(rows, columns=["ts", "value"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def summary(df):
    return df["value"].describe()


def flag_anomalies(df, window=21, z=3.5):
    """Flags points that jump away from the local trend.
    residual = value - centred rolling median (removes slow and orbit-periodic trends);
    score = residual / (1.4826 * MAD of all residuals). 'zscore' keeps the old column name.
    The first and last window//2 points are never flagged (not enough neighbours to judge)."""
    out = df.copy()
    resid = out["value"] - out["value"].rolling(window, center=True, min_periods=window).median()
    mad = (resid - resid.median()).abs().median() * 1.4826
    floor = 0.05 * out["value"].std()          # a near-noise-free (quantised) signal must not make the scale ~0
    mad = max(mad if mad == mad else 0.0, floor) or 1.0
    out["zscore"] = resid / mad
    out["anomaly"] = out["zscore"].abs() > z
    return out


def limit_violations(df, warn, crit, bad_when="high"):
    v = df["value"]
    if bad_when == "high":
        return dict(warn=int(((v >= warn) & (v < crit)).sum()), crit=int((v >= crit).sum()))
    return dict(warn=int(((v <= warn) & (v > crit)).sum()), crit=int((v <= crit).sum()))


def pass_success_rate(passes):
    """passes: list of dicts with frames_rx. Share of passes that received >=1 frame."""
    if not passes:
        return 0.0
    return sum(1 for p in passes if p.get("frames_rx", 0) > 0) / len(passes)
