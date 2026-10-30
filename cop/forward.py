"""Node-side store-and-forward: SQLite outbox survives reboots; replays oldest-first with replayed=True.

    pub = Forwarder("node.db", mqtt_publish, resign=lambda b: sign(Detection(**b), node_key))
    pub.send("cop/detections/air", signed_msg)
    pub.flush()                                # call periodically
"""
import json
import sqlite3
import time


class Forwarder:
    def __init__(self, path, publish, max_rows=50_000, resign=None):
        """resign(body_dict) -> signed msg. Used to mark replays; without it, replays are sent unmodified."""
        self.resign = resign
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, topic TEXT, payload TEXT, t REAL)")
        self.db.commit()
        self.publish, self.max_rows = publish, max_rows

    def send(self, topic, msg: dict):
        if self.pending() == 0 and self._try(topic, msg):
            return True
        self.db.execute("INSERT INTO outbox (topic, payload, t) VALUES (?, ?, ?)", (topic, json.dumps(msg), time.time()))
        self.db.execute("DELETE FROM outbox WHERE id IN (SELECT id FROM outbox ORDER BY id DESC LIMIT -1 OFFSET ?)", (self.max_rows,))
        self.db.commit()
        return False

    def _try(self, topic, msg):
        try:
            return bool(self.publish(topic, json.dumps(msg).encode()))
        except OSError:
            return False

    def flush(self, limit=200):
        sent = 0
        for rid, topic, payload, _ in self.db.execute("SELECT * FROM outbox ORDER BY id LIMIT ?", (limit,)).fetchall():
            msg = json.loads(payload)
            if self.resign:                          # signature covers the body, so re-sign after flagging
                msg = self.resign({**msg["body"], "replayed": True})
            if not self._try(topic, msg):
                break
            self.db.execute("DELETE FROM outbox WHERE id = ?", (rid,))
            sent += 1
        self.db.commit()
        return sent

    def pending(self):
        return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
