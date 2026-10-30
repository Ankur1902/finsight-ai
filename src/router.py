"""Cost-aware model routing: cheap model for lookups, strong model for
comparisons and reasoning, automatic escalation if the cheap call fails."""
from __future__ import annotations

import re
import threading

from .errors import GenerationError
from .query_planner import COMPARE

_COMPLEX = re.compile(
    r"\b(why|explain|analy[sz]e|driver\w*|implication\w*|impact|reconcile|outlook|guidance|risk\w*|"
    r"strateg\w*|margin\w*\s+(?:expansion|pressure)|growth\s+rate|how\s+much\s+(?:did|has).*(?:change|grow))\b", re.I)
_PERIOD = re.compile(r"\bq[1-4]\b|fy\s?\d{2,4}|20\d\d", re.I)


def classify(question: str) -> str:
    """'simple' = single fact lookup; 'complex' = needs synthesis or comparison."""
    q = question or ""
    if COMPARE.search(q) or _COMPLEX.search(q) or len(q) > 220 or len(set(_PERIOD.findall(q.lower()))) >= 3:
        return "complex"
    return "simple"


def question_from_prompt(user: str) -> str:
    return user.rsplit("Question:", 1)[-1].strip()


class RoutedLLM:
    def __init__(self, cheap, strong):
        self.cheap, self.strong = cheap, strong
        self.name = f"router:{cheap.name}>{strong.name}"
        self._local = threading.local()

    @property
    def last_route(self) -> str | None:
        return getattr(self._local, "route", None)

    @property
    def last_model(self) -> str | None:
        return getattr(self._local, "model", None)

    def generate(self, system, user, max_tokens=None):
        tier = classify(question_from_prompt(user))
        if tier == "simple":
            try:
                out = self.cheap.generate(system, user, max_tokens)
                self._local.route, self._local.model = "cheap", self.cheap.name
                return out
            except GenerationError:
                tier = "escalated"
        out = self.strong.generate(system, user, max_tokens)
        self._local.route, self._local.model = ("strong" if tier == "complex" else "escalated"), self.strong.name
        return out

    def generate_json(self, system, user, schema, max_tokens=4096):
        # Structured extraction is accuracy-critical: always the strong model.
        self._local.route, self._local.model = "strong", self.strong.name
        return self.strong.generate_json(system, user, schema, max_tokens)
