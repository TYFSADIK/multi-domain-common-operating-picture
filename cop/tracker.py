"""2D constant-velocity Kalman tracker for the COP: association by Mahalanobis gate, per-domain tracks.

Detections from different domains of the same kind (e.g. acoustic + radar on a UAV) fuse into one track.
Node weight (from ClockMonitor) inflates measurement noise: weight w -> R / w.
"""
from dataclasses import dataclass, field
from itertools import count

import numpy as np

_ids = count(1)
GATE = 13.8   # chi2(2) at 99.9%


@dataclass
class Track:
    x: np.ndarray
    P: np.ndarray
    t: float
    kind: str
    domain: str
    id: int = field(default_factory=lambda: next(_ids))
    hits: int = 1
    last_update: float = 0.0
    nodes: set = field(default_factory=set)

    def predict(self, t, q=0.5):
        dt = max(0.0, t - self.t)
        if dt == 0:
            return
        F = np.eye(4); F[0, 2] = F[1, 3] = dt
        G = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
        self.x, self.P, self.t = F @ self.x, F @ self.P @ F.T + G @ G.T * q * q, t

    def innovation(self, z, R):
        H = np.zeros((2, 4)); H[0, 0] = H[1, 1] = 1
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        return y, S, H


class COPTracker:
    def __init__(self, drop_after_s=30.0):
        self.tracks: list[Track] = []
        self.drop_after_s = drop_after_s

    def update(self, t, e, n, sigma, kind, domain, node, weight=1.0):
        z = np.array([e, n])
        R = np.eye(2) * sigma ** 2 / max(weight, 1e-3)
        best, best_d2 = None, GATE
        for tr in self.tracks:
            if tr.kind != kind:
                continue
            tr.predict(t)
            y, S, _ = tr.innovation(z, R)
            d2 = float(y @ np.linalg.solve(S, y))
            if d2 < best_d2:
                best, best_d2 = tr, d2
        if best is None:
            tr = Track(np.array([e, n, 0, 0], float), np.diag([sigma ** 2, sigma ** 2, 25, 25]), t, kind, domain)
            tr.nodes.add(node); tr.last_update = t
            self.tracks.append(tr)
            return tr
        y, S, H = best.innovation(z, R)
        K = best.P @ H.T @ np.linalg.inv(S)
        best.x = best.x + K @ y
        best.P = (np.eye(4) - K @ H) @ best.P
        best.hits += 1
        best.last_update = t
        best.nodes.add(node)
        return best

    def prune(self, now):
        self.tracks = [t for t in self.tracks if now - t.last_update <= self.drop_after_s]

    def snapshot(self):
        return [{"id": t.id, "kind": t.kind, "domain": t.domain, "e": round(float(t.x[0]), 1), "n": round(float(t.x[1]), 1),
                 "ve": round(float(t.x[2]), 2), "vn": round(float(t.x[3]), 2), "hits": t.hits,
                 "sigma_m": round(float(np.sqrt(t.P[0, 0])), 1), "nodes": sorted(t.nodes)} for t in self.tracks]
