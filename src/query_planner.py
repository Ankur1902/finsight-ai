"""Deterministic query understanding: which company / fiscal period(s) a
question targets, whether it is a comparison, and how to resolve follow-ups.

This is the planning step an agent would do, but rule-based: it is instant,
testable and never hallucinates a filter, which matters when the generator is a
small local model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COMPANY_PATTERNS: dict[str, list[str]] = {
    "microsoft": [r"\bmicrosoft\b", r"\bmsft\b"],
    "meta": [r"\bmeta\b", r"\bmeta platforms\b"],
    "nvda": [r"\bnvidia\b", r"\bnvda\b"],
}
# Product names imply the company when no company is named explicitly.
PRODUCT_HINTS: dict[str, list[str]] = {
    "microsoft": [r"\bazure\b", r"\bcopilot\b", r"\bgithub\b", r"\blinkedin\b", r"\bxbox\b", r"\bm365\b"],
    "meta": [r"\binstagram\b", r"\bwhatsapp\b", r"\bfacebook\b", r"\breality labs\b", r"\bthreads\b", r"\bllama\b"],
    "nvda": [r"\bblackwell\b", r"\bhopper\b", r"\bgeforce\b", r"\bcuda\b", r"\bh20\b", r"\brubin\b"],
}

_ORD = {"first": "1", "second": "2", "third": "3", "fourth": "4", "1st": "1", "2nd": "2", "3rd": "3", "4th": "4"}
_Q = r"(?:q([1-4])|(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter)"
_Y = r"(?:fy\s?|fiscal\s+(?:year\s+)?)?'?(20\d\d|\d\d)\b"

PERIOD_PATTERNS = [
    re.compile(rf"{_Q}\s*(?:of\s+)?,?\s*{_Y}", re.I),  # Q1 2025, Q1 FY25, first quarter of fiscal 2026
    re.compile(rf"\b(?:fy\s?|fiscal\s+(?:year\s+)?)'?(20\d\d|\d\d)\s+{_Q}", re.I),  # FY25 Q1
]
YEAR_ONLY = re.compile(r"\b(?:fy\s?|fiscal\s+(?:year\s+)?)'?(20\d\d|\d\d)\b|\b(20\d\d)\b", re.I)
LATEST = re.compile(r"\b(latest|most recent|newest|last reported|current quarter)\b", re.I)
COMPARE = re.compile(
    r"\b(compar\w*|versus|vs\.?|trend\w*|over time|across|quarter[- ]over[- ]quarter|"
    r"each quarter|every quarter|evolv\w*|changed?|progress\w*)\b",
    re.I,
)
FOLLOW_UP = re.compile(
    r"^(and|what about|how about|same for|also|then|ok|okay)\b|\b(it|its|they|their|them|that quarter|"
    r"previous quarter|prior quarter|last quarter|next quarter)\b",
    re.I,
)


def _year(token: str) -> str:
    return token if len(token) == 4 else f"20{token}"


@dataclass(frozen=True)
class Target:
    company: str | None = None
    quarter: str | None = None
    year: str | None = None

    def label(self) -> str:
        parts = [self.company or "any company"]
        if self.quarter or self.year:
            parts.append(f"{self.quarter or ''} FY{self.year or ''}".strip())
        return " ".join(parts)


@dataclass
class QueryPlan:
    question: str
    companies: list[str] = field(default_factory=list)
    periods: list[tuple[str | None, str | None]] = field(default_factory=list)
    wants_latest: bool = False
    is_comparison: bool = False
    inherited: bool = False
    targets: list[Target] = field(default_factory=list)


def detect_companies(text: str) -> list[str]:
    found = [c for c, pats in COMPANY_PATTERNS.items() if any(re.search(p, text, re.I) for p in pats)]
    if found:
        return found
    return [c for c, pats in PRODUCT_HINTS.items() if any(re.search(p, text, re.I) for p in pats)]


def detect_periods(text: str) -> list[tuple[str | None, str | None]]:
    periods: list[tuple[str | None, str | None]] = []
    spans: list[tuple[int, int]] = []

    for pattern in PERIOD_PATTERNS:
        for m in pattern.finditer(text):
            groups = [g for g in m.groups()]
            if pattern is PERIOD_PATTERNS[0]:
                q_num, q_word, year = groups
            else:
                year, q_num, q_word = groups
            quarter = f"Q{q_num or _ORD[q_word.lower()]}"
            item = (quarter, _year(year))
            if item not in periods:
                periods.append(item)
            spans.append(m.span())

    # Bare quarter ("in Q3") with no year.
    for m in re.finditer(rf"\b{_Q}", text, re.I):
        if any(s <= m.start() < e for s, e in spans):
            continue
        quarter = f"Q{m.group(1) or _ORD[m.group(2).lower()]}"
        periods.append((quarter, None))
        spans.append(m.span())

    # Bare year ("in fiscal 2026", "2025").
    for m in YEAR_ONLY.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        year = _year(m.group(1) or m.group(2))
        if (None, year) not in periods:
            periods.append((None, year))

    return periods


def plan_query(
    question: str,
    catalog: dict[str, list[tuple[str, str]]] | None = None,
    previous: QueryPlan | None = None,
) -> QueryPlan:
    """Build retrieval targets.

    catalog maps company -> [(quarter, year), ...] ordered oldest -> newest;
    it is used to expand "latest" and "trend across quarters" questions.
    """
    catalog = catalog or {}
    plan = QueryPlan(
        question=question,
        companies=detect_companies(question),
        periods=detect_periods(question),
        wants_latest=bool(LATEST.search(question)),
        is_comparison=bool(COMPARE.search(question)),
    )

    # Follow-up turns ("what about their capex?") inherit missing slots.
    if previous and FOLLOW_UP.search(question):
        if not plan.companies and previous.companies:
            plan.companies = list(previous.companies)
            plan.inherited = True
        if not plan.periods and not plan.wants_latest and previous.periods:
            plan.periods = list(previous.periods)
            plan.inherited = True

    # A future outlook year is not a second reporting period.
    if any(q and y for q, y in plan.periods):
        outlook_years = set(re.findall(r"\b(20\d\d)\s+(?:capex|capital expenditure|revenue|earnings)?\s*(?:guidance|outlook)", question, re.I))
        plan.periods = [(q, y) for q, y in plan.periods if q or y not in outlook_years]

    plan.is_comparison = plan.is_comparison or len(plan.companies) > 1 or len(plan.periods) > 1

    # Bind explicitly named companies and periods within comparison clauses.
    # Shared periods still use the standard expansion below.
    if len(plan.companies) > 1 and len(plan.periods) > 1:
        bound = []
        for clause in re.split(r"\b(?:versus|vs\.?|with|and)\b", question, flags=re.I):
            named = detect_companies(clause)
            periods = detect_periods(clause)
            if len(named) == 1 and periods:
                bound.extend(Target(named[0], q, y) for q, y in periods)
        if set(t.company for t in bound) == set(plan.companies):
            plan.targets = list(dict.fromkeys(bound))
            return plan

    companies: list[str | None] = list(plan.companies) or [None]
    targets: list[Target] = []
    for company in companies:
        available = catalog.get(company or "", [])
        if plan.periods:
            for quarter, year in plan.periods:
                targets.append(Target(company, quarter, year))
        elif plan.wants_latest and available:
            quarter, year = available[-1]
            targets.append(Target(company, quarter, year))
        elif plan.is_comparison and company and available:
            # "How has Azure growth trended?" -> one bucket per reported quarter.
            targets.extend(Target(company, q, y) for q, y in available[-6:])
        else:
            targets.append(Target(company))

    plan.targets = targets
    return plan
