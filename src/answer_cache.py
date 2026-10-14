"""Bounded in-memory cache of validated replies; never caches feedback tokens."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
from math import isfinite


class AnswerCache:
    def __init__(self, capacity=128, ttl=600):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("Cache capacity must be a positive integer")
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not isfinite(ttl) or ttl <= 0:
            raise ValueError("Cache TTL must be positive and finite")
        self.capacity, self.ttl = capacity, ttl
        self.rows = OrderedDict()
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            row = self.rows.get(key)
            if row is None:
                return None
            if monotonic() - row[0] >= self.ttl:
                del self.rows[key]
                return None
            self.rows.move_to_end(key)
            return deepcopy(row[1])

    def put(self, key, response):
        if response.blocked or response.flags:
            return
        with self.lock:
            self.rows[key] = (monotonic(), deepcopy(response))
            self.rows.move_to_end(key)
            while len(self.rows) > self.capacity:
                self.rows.popitem(last=False)

    def clear(self):
        with self.lock:
            self.rows.clear()


ANSWERS = AnswerCache()
