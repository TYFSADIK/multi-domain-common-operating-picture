"""COP service: MQTT in -> verify -> clock check -> tracker -> evidence log; HTTP out (dashboard + JSON + SSE).

    python -m cop.server --mqtt localhost --keys keys/registry.json
    open http://localhost:8080
"""
import argparse
import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .clock import ClockMonitor
from .schema import verify
from .tracker import COPTracker

STATIC = os.path.join(os.path.dirname(__file__), "static")


class COP:
    def __init__(self, registry, evidence_path="data/evidence.jsonl"):
        self.registry, self.clock, self.trk = registry, ClockMonitor(), COPTracker()
        self.lock = threading.Lock()
        self.alerts, self.rejected = [], 0
        self.evidence_path, self.prev = evidence_path, "0" * 64

    def _evidence(self, rec):
        rec["prev"] = self.prev
        line = json.dumps(rec, sort_keys=True)
        self.prev = hashlib.sha256(line.encode()).hexdigest()
        with open(self.evidence_path, "a") as fh:
            fh.write(line + "\n")

    def ingest(self, msg: dict, rx_t=None):
        rx_t = rx_t or time.time()
        d = verify(msg, self.registry)
        with self.lock:
            if d is None:
                self.rejected += 1
                self._evidence({"event": "rejected", "rx": rx_t})
                return None
            status, t, w = self.clock.observe(d.node, d.t, rx_t, d.replayed)
            if status == "skewed":
                self.alerts.append({"t": rx_t, "type": "clock_skew", "node": d.node})
            tr = self.trk.update(t, d.e, d.n, d.sigma_m, d.kind, d.domain, d.node, w)
            self._evidence({"event": "fused", "node": d.node, "seq": d.seq, "track": tr.id, "clock": status, "rx": rx_t})
            return tr.id

    def state(self):
        with self.lock:
            self.trk.prune(time.time())
            return {"tracks": self.trk.snapshot(), "alerts": self.alerts[-50:], "rejected": self.rejected}


def make_handler(cop):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/api/state":
                body = json.dumps(cop.state()).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.end_headers(); self.wfile.write(body)
            elif self.path == "/events":
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                while True:
                    self.wfile.write(f"data: {json.dumps(cop.state())}\n\n".encode()); self.wfile.flush()
                    time.sleep(1)
            else:
                with open(os.path.join(STATIC, "index.html"), "rb") as fh:
                    body = fh.read()
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
                self.wfile.write(body)
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt", default="localhost")
    ap.add_argument("--keys", default="keys/registry.json", help='{"node-id": "<ed25519 pub hex>"}')
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    reg = {k: Ed25519PublicKey.from_public_bytes(bytes.fromhex(v)) for k, v in json.load(open(a.keys)).items()}
    os.makedirs("data", exist_ok=True)
    cop = COP(reg)
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_message = lambda _c, _u, m: cop.ingest(json.loads(m.payload))
    c.connect(a.mqtt)
    c.subscribe("cop/detections/#", qos=1)
    c.loop_start()
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(cop)).serve_forever()


if __name__ == "__main__":
    main()
