"""Clock-corruption defence (Run T5).

For live (non-replayed) messages, offset = rx_time - node_time should be small and
stable (link latency). Track a robust per-node baseline; if a node's recent
offsets jump by more than `max_skew_s`, mark it SKEWED: its detections are either
re-timed with the estimated skew (if the skew is stable) or down-weighted.
Replayed messages are exempt from the live check (they are old by design) but are
re-timed with the skew that was in force when they were recorded, if known.
"""
from collections import defaultdict, deque
import statistics


class ClockMonitor:
    def __init__(self, window=15, max_skew_s=2.0, min_samples=5):
        self.devs = defaultdict(lambda: deque(maxlen=window))   # offset minus baseline
        self.learn = defaultdict(list)
        self.baseline = {}
        self.max_skew_s, self.min_samples = max_skew_s, min_samples

    def observe(self, node, node_t, rx_t, replayed=False):
        """Returns (status, corrected_t, weight)."""
        if replayed:
            skew = self.current_skew(node)
            return ("replayed", node_t + skew, 0.7 if abs(skew) > self.max_skew_s else 1.0)
        off = rx_t - node_t
        if node not in self.baseline:
            self.learn[node].append(off)
            if len(self.learn[node]) >= self.min_samples:
                self.baseline[node] = statistics.median(self.learn.pop(node))
            return ("learning", node_t, 1.0)
        dev = off - self.baseline[node]
        self.devs[node].append(dev)
        if abs(dev) > self.max_skew_s:
            # Judge each message on its own: never let a step leak into the baseline.
            recent = list(self.devs[node])[-self.min_samples:]
            stable = len(recent) == self.min_samples and all(abs(d) > self.max_skew_s for d in recent)                 and statistics.pstdev(recent) < 0.5
            # Receive time is trustworthy (broker clock); re-time from it.
            return ("skewed", rx_t - self.baseline[node], 0.5 if stable else 0.2)
        self.baseline[node] = 0.98 * self.baseline[node] + 0.02 * off   # follow slow latency drift only
        return ("ok", node_t, 1.0)

    def current_skew(self, node):
        recent = list(self.devs.get(node, []))[-self.min_samples:]
        return statistics.median(recent) if recent else 0.0
