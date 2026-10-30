"""Run: python demo.py  -> Run T5 replay: 3 nodes on a walked perimeter, node B's clock jumps +47 s mid-run."""
import math
import os
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cop.schema import Detection, sign
from cop.server import COP

keys = {n: Ed25519PrivateKey.generate() for n in ("seis-A", "seis-B", "seis-C")}
reg = {n: k.public_key() for n, k in keys.items()}
cop = COP(reg, evidence_path=os.path.join(tempfile.mkdtemp(), "evidence.jsonl"))
T0 = 1_760_000_000
ids = set()
for i in range(240):
    t = T0 + i
    e, n = 300 * math.cos(i / 40), 300 * math.sin(i / 40)      # walking the perimeter
    for k, (node, key) in enumerate(keys.items()):
        if i % 3 != k:
            continue
        skew = 47 if node == "seis-B" and 100 <= i < 160 else 0
        d = Detection(node, i, t + skew, "ground", "footsteps", e + 3 * math.sin(i), n + 3 * math.cos(i), 8.0, 0.8)
        ids.add(cop.ingest(sign(d, key), rx_t=t + 0.3))
forged = sign(Detection("seis-A", 999, T0, "ground", "vehicle", 0, 0, 5, 1), Ed25519PrivateKey.generate())
cop.ingest(forged, rx_t=T0)
s = {"tracks": cop.trk.snapshot(), "alerts": cop.alerts, "rejected": cop.rejected}
print(f"track ids used: {sorted(i for i in ids if i)}  (target: exactly one)")
print(f"clock-skew alerts: {len(s['alerts'])} on {sorted({a['node'] for a in s['alerts']})}; forged messages rejected: {s['rejected']}")
