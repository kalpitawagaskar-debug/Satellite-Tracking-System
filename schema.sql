CREATE TABLE IF NOT EXISTS satellites (
    norad_id INTEGER PRIMARY KEY,
    name     TEXT NOT NULL
);
-- Raw frames exactly as received (hex). Decoding is satellite-specific.
CREATE TABLE IF NOT EXISTS frames (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    norad_id       INTEGER NOT NULL REFERENCES satellites(norad_id),
    rx_time        TEXT NOT NULL,          -- ISO-8601 UTC, ground-station reception time
    frame_hex      TEXT NOT NULL,
    observer       TEXT,
    observation_id INTEGER,
    UNIQUE (norad_id, rx_time, frame_hex)
);
CREATE INDEX IF NOT EXISTS idx_frames_sat_time ON frames (norad_id, rx_time);
-- Decoded values (one row per metric per timestamp).
CREATE TABLE IF NOT EXISTS housekeeping (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    norad_id INTEGER NOT NULL,
    ts       TEXT NOT NULL,
    metric   TEXT NOT NULL,
    value    REAL NOT NULL,
    UNIQUE (norad_id, ts, metric)
);
CREATE INDEX IF NOT EXISTS idx_hk ON housekeeping (norad_id, metric, ts);
CREATE TABLE IF NOT EXISTS passes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    norad_id   INTEGER NOT NULL,
    aos        TEXT NOT NULL,
    los        TEXT NOT NULL,
    max_el     REAL NOT NULL,
    frames_rx  INTEGER NOT NULL DEFAULT 0,
    decoded    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (norad_id, aos)
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT NOT NULL,
    message TEXT NOT NULL
);

-- OPS-SAT-AD benchmark: one row per labelled telemetry segment with 18 handcrafted features.
CREATE TABLE IF NOT EXISTS ops_segments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset          TEXT NOT NULL,
    segment          INTEGER NOT NULL,
    channel          TEXT NOT NULL,
    sampling         REAL,
    train            INTEGER NOT NULL,          -- 1 = training split, 0 = test split (as supplied)
    anomaly          INTEGER NOT NULL,          -- 1 = labelled anomalous
    duration REAL, len REAL, mean REAL, var REAL, std REAL, kurtosis REAL, skew REAL,
    n_peaks REAL, smooth10_n_peaks REAL, smooth20_n_peaks REAL, diff_peaks REAL, diff2_peaks REAL,
    diff_var REAL, diff2_var REAL, gaps_squared REAL, len_weighted REAL,
    var_div_duration REAL, var_div_len REAL,
    UNIQUE (dataset, segment)
);
