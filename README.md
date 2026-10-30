# Multi-Domain Common Operating Picture

Private research repo. The fusion layer that ties every sensor build together. Signed detections arrive over MQTT (Zenoh evaluated), store-and-forward carries them through dead links, and one Kalman tracker feeds a single dashboard.

Full write-up: [`docs/project-page.md`](docs/project-page.md)

## Architecture

```
air (passive radar, acoustic) ─┐
water (hydrophone)             ├─ Ed25519-signed Detection ─ node SQLite outbox ─ MQTT ─> COP
ground (seismic mesh)         ─┘                                                          │
                       verify sig ─> ClockMonitor (T5) ─> Kalman tracker ─> hash-chained evidence log
                                                                     └──> dashboard (SSE) + alert queue
```

## What's here

| File | Purpose |
|---|---|
| `cop/schema.py` | `Detection` envelope, canonical JSON, Ed25519 sign and verify against a node key registry |
| `cop/clock.py` | **Clock-corruption defence**: per-node latency baseline. Messages off by more than 2 s are flagged, re-timed from broker receive time, and down-weighted, and the baseline never absorbs a step |
| `cop/tracker.py` | 2D constant-velocity Kalman tracker with Mahalanobis gating. Node weight inflates R. Cross-domain fusion by kind |
| `cop/forward.py` | Node-side SQLite outbox that survives reboots. Replays are flagged and **re-signed** |
| `cop/server.py` | MQTT subscriber, then verify, clock check, fuse, and evidence log. HTTP `/api/state`, `/events` (SSE), dashboard |
| `cop/static/index.html` | Range-ring map with tracks coloured by domain, an alert queue, and a rejected-message count |

## Quickstart

```bash
pip install -r requirements.txt
python demo.py               # Run T5: node B jumps +47 s mid-run -> still ONE track id, skew flagged, forgery rejected
python -m unittest -v
mosquitto -v & python -m cop.server --keys keys/registry.json   # live, then open http://localhost:8080
```

## Next steps
- [ ] Node adapters: `acoustic-drone-detector` bearings, `sky-passive-radar-node` plots, `ground-seismic-perimeter-mesh` gateway, `water-...` detections, all to `Detection`
- [ ] Runs T1–T4 (clean link, degraded link via `tc netem`, full outage and recovery, node/service failure) as scripted tests
- [ ] Mosquitto with TLS + per-node client certs, and ACLs so a node can only publish to its own topic
- [ ] Zenoh comparison under `tc netem` loss (latency, recovery time)
- [ ] Forward evidence-log checkpoints to `decision-black-box`
