import math
import os
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cop.clock import ClockMonitor
from cop.forward import Forwarder
from cop.schema import Detection, sign, verify
from cop.server import COP


class TestCOP(unittest.TestCase):
    def test_signature(self):
        k = Ed25519PrivateKey.generate()
        m = sign(Detection("n1", 1, 0.0, "air", "uav", 1, 2, 5, 0.9), k)
        self.assertIsNotNone(verify(m, {"n1": k.public_key()}))
        m["body"]["kind"] = "bird"
        self.assertIsNone(verify(m, {"n1": k.public_key()}))
        self.assertIsNone(verify(m, {}))

    def test_clock_skew_detected_and_corrected(self):
        c = ClockMonitor()
        for i in range(10):
            self.assertIn(c.observe("a", i, i + 0.2)[0], ("learning", "ok"))
        st = [c.observe("a", i + 47, i + 0.2) for i in range(10, 20)]
        self.assertEqual(st[-1][0], "skewed")
        self.assertAlmostEqual(st[-1][1], 19, delta=0.5)   # re-timed back onto true time

    def test_t5_single_track(self):
        keys = {n: Ed25519PrivateKey.generate() for n in "ABC"}
        cop = COP({n: k.public_key() for n, k in keys.items()}, os.path.join(tempfile.mkdtemp(), "e.jsonl"))
        ids = set()
        for i in range(200):
            for j, (n, k) in enumerate(keys.items()):
                if i % 3 == j:
                    skew = 47 if n == "B" and 80 <= i < 140 else 0
                    d = Detection(n, i, 1000 + i + skew, "ground", "footsteps", 300 * math.cos(i / 40), 300 * math.sin(i / 40), 8, 0.8)
                    ids.add(cop.ingest(sign(d, k), rx_t=1000 + i + 0.3))
        self.assertEqual(len(ids), 1)

    def test_store_and_forward(self):
        import json
        k = Ed25519PrivateKey.generate()
        link = {"up": False, "got": []}
        f = Forwarder(os.path.join(tempfile.mkdtemp(), "n.db"), lambda t, p: link["up"] and (link["got"].append(p) or True),
                      resign=lambda b: sign(Detection(**b), k))
        for i in range(5):
            f.send("cop/detections/air", sign(Detection("n1", i, 0.0, "air", "uav", 0, 0, 5, 0.9), k))
        self.assertEqual(f.pending(), 5)
        link["up"] = True
        self.assertEqual(f.flush(), 5)
        self.assertEqual(f.pending(), 0)
        d = verify(json.loads(link["got"][0]), {"n1": k.public_key()})
        self.assertTrue(d is not None and d.replayed)


if __name__ == "__main__":
    unittest.main()
