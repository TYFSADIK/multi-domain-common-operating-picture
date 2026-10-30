"""Signed detection envelope shared by every sensor node (air, water, ground).

Canonical JSON (sorted keys, no whitespace) is signed with the node's Ed25519 key.
The COP holds a registry of node public keys; an unknown or bad signature is dropped
and logged, never fused.
"""
from dataclasses import asdict, dataclass, field
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


@dataclass
class Detection:
    node: str
    seq: int
    t: float                    # node clock, UTC seconds (PPS-disciplined)
    domain: str                 # air | water | ground
    kind: str                   # e.g. "uav", "vessel", "vehicle", "footsteps"
    e: float                    # site ENU metres (nodes convert their own measurement)
    n: float
    sigma_m: float
    conf: float
    replayed: bool = False
    extra: dict = field(default_factory=dict)

    def canonical(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()


def sign(d: Detection, key: Ed25519PrivateKey) -> dict:
    return {"body": asdict(d), "sig": key.sign(d.canonical()).hex()}


def verify(msg: dict, registry: dict[str, Ed25519PublicKey]) -> Detection | None:
    try:
        d = Detection(**msg["body"])
        registry[d.node].verify(bytes.fromhex(msg["sig"]), d.canonical())
        return d
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return None
