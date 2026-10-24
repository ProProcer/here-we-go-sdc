"""Bounded, expiring JSON results. Keys are hashes; input profiles are never saved."""

import copy
import hashlib
import json
import threading
import time
from pathlib import Path

from src.intelligence.storage import atomic_json


class ResultCache:
    def __init__(self, path=None, *, ttl=604800, limit=64, now=time.time):
        self.path = Path(path) if path else None
        self.ttl, self.limit, self.now = ttl, limit, now
        self.lock = threading.RLock()
        self.items = {}
        if self.path:
            try:
                if self.path.stat().st_size <= 8 * 1024 * 1024:
                    value = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(value, dict) and value.get("version") == 1 and isinstance(value.get("items"), dict):
                        self.items = {key: row for key, row in value["items"].items()
                                      if isinstance(row, dict) and isinstance(row.get("at"), (int, float))
                                      and 0 <= self.now() - row["at"] < self.ttl and "value" in row}
                        self.items = dict(list(self.items.items())[-limit:])
            except (OSError, ValueError, TypeError):
                pass

    @staticmethod
    def key(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def get(self, key):
        with self.lock:
            row = self.items.get(key)
            if not row or not 0 <= self.now() - row["at"] < self.ttl:
                self.items.pop(key, None)
                return None
            return copy.deepcopy(row["value"])

    def put(self, key, value):
        with self.lock:
            self.items.pop(key, None)
            self.items[key] = {"at": self.now(), "value": copy.deepcopy(value)}
            self.items = {key: row for key, row in self.items.items() if 0 <= self.now() - row["at"] < self.ttl}
            while len(self.items) > self.limit:
                self.items.pop(next(iter(self.items)))
            if self.path:
                try:
                    atomic_json(self.path, {"version": 1, "items": self.items})
                except OSError:
                    pass  # Disk failure must not discard a completed assessment.
