"""GUI-free anomaly detector for the OPS-SAT-AD segment features (numpy only).

Model: logistic regression trained by gradient descent on log-scaled, standardised features,
with class weights (anomalies are only ~20 % of segments) and a decision threshold chosen on the
TRAINING split. The supplied train/test split is used as-is, the test split is touched once.
Also reports two reference points so accuracy is not misread:
  * "always nominal": accuracy of a detector that never raises an alarm
  * an unsupervised robust z-score detector (no labels)
Caveat: the benchmark split is a random stratified split, so near-duplicate segments can sit on both
sides. Scores on unseen satellites/channels will probably be lower.
"""
import numpy as np
from db import OPS_FEATURES


def _tf(x):
    return np.sign(x) * np.log1p(np.abs(x))


def confusion(y, p):
    y, p = np.asarray(y).astype(int), np.asarray(p).astype(int)
    tp, fp = int(((y == 1) & (p == 1)).sum()), int(((y == 0) & (p == 1)).sum())
    fn, tn = int(((y == 1) & (p == 0)).sum()), int(((y == 0) & (p == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=prec, recall=rec, f1=f1,
                accuracy=(tp + tn) / max(1, len(y)))


class LogisticDetector:
    def __init__(self, l2=1.0, lr=0.1, iters=3000):
        self.l2, self.lr, self.iters = l2, lr, iters
        self.w = self.b = self.mu = self.sd = None
        self.threshold = 0.5

    def _z(self, X):
        return (_tf(np.asarray(X, float)) - self.mu) / self.sd

    def fit(self, X, y):
        X, y = np.asarray(X, float), np.asarray(y, float)
        if len(set(y.tolist())) < 2:
            raise ValueError("training data needs both normal and anomalous segments")
        T = _tf(X)
        self.mu, self.sd = T.mean(0), T.std(0) + 1e-9
        Z = (T - self.mu) / self.sd
        sw = np.where(y == 1, (len(y) - y.sum()) / y.sum(), 1.0)
        w, b = np.zeros(Z.shape[1]), 0.0
        for _ in range(self.iters):
            g = (1 / (1 + np.exp(-(Z @ w + b))) - y) * sw
            w -= self.lr * ((Z.T @ g) / len(y) + self.l2 * w / len(y))
            b -= self.lr * g.mean()
        self.w, self.b = w, b
        ptr = self.proba(X)
        self.threshold = max(np.linspace(0.05, 0.95, 91),
                             key=lambda t: confusion(y, ptr > t)["f1"])
        return self

    def proba(self, X):
        return 1 / (1 + np.exp(-(self._z(X) @ self.w + self.b)))

    def predict(self, X):
        return (self.proba(X) > self.threshold).astype(int)


def _robust_z_detector(Xtr, Xte, contamination=0.2):
    A, B = _tf(Xtr), _tf(Xte)
    med = np.median(A, 0)
    mad = np.median(np.abs(A - med), 0) * 1.4826
    mad = np.where(mad == 0, A.std(0) + 1e-9, mad)
    score = lambda M: np.clip(np.abs((M - med) / mad), 0, 10).mean(1)  # noqa: E731
    return (score(B) > np.percentile(score(A), 100 * (1 - contamination))).astype(int)


SIZE_FEATURES = {"len", "duration", "len_weighted", "var_div_len", "var_div_duration", "gaps_squared"}


def evaluate_rows(rows, features=OPS_FEATURES, _ablation=True):
    """rows: list of dicts from Database.ops_segments(). Returns a result dict for the UI."""
    if not rows:
        raise ValueError("no OPS-SAT-AD segments in the database: import dataset.csv first")
    tr = [r for r in rows if r["train"] == 1]
    te = [r for r in rows if r["train"] == 0]
    if len(tr) < 20 or len(te) < 20:
        raise ValueError(f"need at least 20 train and 20 test segments (have {len(tr)} / {len(te)})")
    mat = lambda rs: np.array([[r[f] for f in features] for r in rs], float)  # noqa: E731
    Xtr, Xte = mat(tr), mat(te)
    ytr, yte = np.array([r["anomaly"] for r in tr]), np.array([r["anomaly"] for r in te])
    det = LogisticDetector().fit(Xtr, ytr)
    model = confusion(yte, det.predict(Xte))
    model["threshold"] = round(float(det.threshold), 2)
    chan = {}
    for r in rows:
        n, a = chan.get(r["channel"], (0, 0))
        chan[r["channel"]] = (n + 1, a + r["anomaly"])
    order = np.argsort(-np.abs(det.w))[:5]
    no_size = None
    if _ablation:      # does the model only learn how long a segment is? retrain without size-related features
        keep = [f for f in features if f not in SIZE_FEATURES]
        no_size = evaluate_rows(rows, keep, _ablation=False)["model"] if keep else None
    return dict(
        without_size_features=no_size,
        n_train=len(tr), n_test=len(te),
        anomaly_rate_train=float(ytr.mean()), anomaly_rate_test=float(yte.mean()),
        model=model,
        always_nominal_accuracy=float((yte == 0).mean()),
        unsupervised=confusion(yte, _robust_z_detector(Xtr, Xte)),
        top_features=[(features[i], round(float(det.w[i]), 2)) for i in order],
        channels={c: (n, a / n) for c, (n, a) in sorted(chan.items())},
    )
