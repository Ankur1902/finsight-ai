"""Semantic answer cache without an embedding model.

Paraphrases ("Azure growth in Q2 FY25?" vs "How fast did Azure grow in fiscal
Q2 2025?") are matched with hashed character-n-gram cosine similarity, but a hit
additionally requires the same resolved company/period scope, the same numbers
and the same negation words, so a near-duplicate with a different meaning never
reuses an answer. Only validated, unflagged replies are stored."""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic

_NEG = {"not", "no", "never", "without", "decline", "decrease", "fall", "drop", "lower", "down"}
_POS = {"increase", "grow", "growth", "rise", "up", "higher", "gain"}


def _vector(text: str, n: int = 3, dims: int = 4096) -> dict[int, float]:
    t = " " + re.sub(r"[^a-z0-9 ]", " ", text.lower()) + " "
    t = re.sub(r"\s+", " ", t)
    v: dict[int, float] = {}
    for i in range(len(t) - n + 1):
        h = hash(t[i:i + n]) % dims
        v[h] = v.get(h, 0.0) + 1.0
    return v


def _cos(a: dict, b: dict) -> float:
    dot = sum(x * b.get(k, 0.0) for k, x in a.items())
    na, nb = math.sqrt(sum(x * x for x in a.values())), math.sqrt(sum(x * x for x in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _signature(text: str):
    words = set(re.findall(r"[a-z]+", text.lower()))
    return (frozenset(re.findall(r"\d+(?:\.\d+)?", text)), frozenset(words & _NEG), frozenset(words & _POS))


class SemanticCache:
    def __init__(self, capacity: int = 256, ttl: float = 600, threshold: float = 0.9):
        self.capacity, self.ttl, self.threshold = capacity, ttl, threshold
        self.rows: OrderedDict[int, tuple] = OrderedDict()
        self.lock, self._next = RLock(), 0
        self.hits = self.misses = 0

    def get(self, scope: str, question: str):
        vec, sig, now = _vector(question), _signature(question), monotonic()
        with self.lock:
            best, best_id = 0.0, None
            for rid, (ts, s, v, sg, _resp) in list(self.rows.items()):
                if now - ts >= self.ttl:
                    del self.rows[rid]
                    continue
                if s != scope or sg != sig:
                    continue
                sim = _cos(vec, v)
                if sim > best:
                    best, best_id = sim, rid
            if best_id is not None and best >= self.threshold:
                self.hits += 1
                self.rows.move_to_end(best_id)
                resp = deepcopy(self.rows[best_id][4])
                resp.details["semantic_similarity"] = round(best, 3)
                return resp
            self.misses += 1
            return None

    def put(self, scope: str, question: str, response):
        if response.blocked or response.flags:
            return
        with self.lock:
            self._next += 1
            self.rows[self._next] = (monotonic(), scope, _vector(question), _signature(question), deepcopy(response))
            while len(self.rows) > self.capacity:
                self.rows.popitem(last=False)

    def clear(self):
        with self.lock:
            self.rows.clear()
            self.hits = self.misses = 0


SEMANTIC = SemanticCache()
