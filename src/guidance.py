"""Guidance-vs-actual tracker.

Guidance is extracted deterministically from transcript text (so every range
carries an exact quotation and page); actuals come from the validated metric
extractor for the *next* reporting period. The comparison is plain Decimal
arithmetic. Nothing is interpolated: a missing next period or metric yields
`no_actual`, never a guess."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal

METRIC_WORDS = {
    "revenue": r"\brevenue\b", "capex": r"capital expenditures?|\bcapex\b",
    "gross_margin": r"gross margins?", "operating_margin": r"operating margins?",
}
_CUE = re.compile(r"\b(expect|expects|expected|guidance|outlook|anticipate|anticipates|forecast|we(?:'|’)ll|should be)\b", re.I)
_PAST = re.compile(r"\b(?:than|as)\s+expected\b|\b(?:was|were)\s+(?:slightly\s+)?expected\b", re.I)
_SEGMENT = re.compile(r"productivity and business|intelligent cloud|personal computing|family of apps|reality labs|"
                      r"data center|cloud|segment|advertising|\bazure\b|\bgaming\b|\bsearch\b", re.I)
_ANNUAL = re.compile(r"full[- ]year|\bannual|(?:\b20\d\d|\bfy\s?\d{2,4})\s+(?:total\s+)?capital expenditures?", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_NUM = r"(\d+(?:\.\d+)?)"
_RANGE = re.compile(rf"\$?{_NUM}\s*(billion|million)?\s*(?:to|and|-|–)\s*\$?{_NUM}\s*(billion|million)", re.I)
_MONEY = re.compile(rf"\$\s?{_NUM}\s*(billion|million)", re.I)
_PCT_RANGE = re.compile(rf"{_NUM}\s*(?:%|percent)?\s*(?:to|and|-|–)\s*{_NUM}\s*(?:%|percent)", re.I)
_PCT = re.compile(rf"{_NUM}\s*(?:%|percent)", re.I)
_PM_PCT = re.compile(rf"plus or minus {_NUM}\s*(?:%|percent)", re.I)
_PM_BPS = re.compile(rf"plus or minus {_NUM}\s*basis points?", re.I)
_SCALE = {"billion": Decimal(1000), "million": Decimal(1)}  # normalise to USD million


@dataclass
class Guidance:
    metric: str
    low: str
    high: str
    unit: str  # "USD million" | "percent"
    quote: str
    page: int
    source: str
    period: str
    horizon: str = "quarter"  # quarter | full_year (not comparable with one quarter)


def _d(x) -> Decimal:
    return Decimal(str(x))


def parse_sentence(sentence: str) -> tuple[str, Decimal, Decimal, str] | None:
    metric = next((m for m, p in METRIC_WORDS.items() if re.search(p, sentence, re.I)), None)
    if not metric or not _CUE.search(sentence) or not re.search(r"\d", sentence) or _PAST.search(sentence):
        return None
    # The forward-looking cue must come *before* the figure ("we expect revenue of ..."),
    # and long-horizon or non-revenue dollar figures (bookings, opportunity) are not guidance.
    cue, number = _CUE.search(sentence), re.search(r"\d", sentence)
    if cue.start() > number.start() or re.search(r"booking|opportunit|trillion|cumulative|through\s+20\d\d|by\s+20\d\d", sentence, re.I):
        return None
    # Company-level metrics only: segment/product figures are a different measure.
    if _SEGMENT.search(sentence) and not re.search(r"\b(?:total|consolidated|company)\b", sentence, re.I):
        return None
    if metric.endswith("margin") and re.search(r"\bcloud\b", sentence, re.I):
        return None
    if metric in ("gross_margin", "operating_margin"):
        m = _PCT_RANGE.search(sentence)
        if m:
            return metric, _d(m[1]), _d(m[2]), "percent"
        m = _PCT.search(sentence)
        if m:
            c = _d(m[1])
            band = _PM_BPS.search(sentence)
            if band:
                return metric, c - _d(band[1]) / 100, c + _d(band[1]) / 100, "percent"
            return metric, c, c, "percent"
        return None
    m = _RANGE.search(sentence)
    if m:
        unit_lo = (m[2] or m[4]).lower()
        return metric, _d(m[1]) * _SCALE[unit_lo], _d(m[3]) * _SCALE[m[4].lower()], "USD million"
    m = _MONEY.search(sentence)
    if m:
        c = _d(m[1]) * _SCALE[m[2].lower()]
        band = _PM_PCT.search(sentence)
        if band:
            return metric, c * (1 - _d(band[1]) / 100), c * (1 + _d(band[1]) / 100), "USD million"
        if re.search(r"\b(approximately|roughly|about|around)\b", sentence, re.I):
            return metric, c, c, "USD million"
        return None
    return None


def extract_guidance(pages) -> list[Guidance]:
    out: list[Guidance] = []
    seen = set()
    for page in pages:
        text = re.sub(r"\s+", " ", page.page_content)
        for sentence in _SENT.split(text):
            parsed = parse_sentence(sentence)
            if not parsed:
                continue
            metric, lo, hi, unit = parsed
            key = (metric, lo, hi)
            if key in seen:
                continue
            seen.add(key)
            m = page.metadata
            out.append(Guidance(metric, format(lo.normalize(), 'f'), format(hi.normalize(), 'f'), unit, sentence.strip()[:400],
                                m.get("page", 0), m.get("source", ""), m.get("period", ""),
                                "full_year" if _ANNUAL.search(sentence) else "quarter"))
    return out


def _to_unit(value: float, unit: str) -> Decimal:
    v = _d(value)
    return v * 1000 if unit == "USD billion" else v


def compare(guidance: list[Guidance], facts: list[dict], tolerance_pct: Decimal = Decimal("0.5")) -> list[dict]:
    """Match each guidance item to the actual of the same metric and classify."""
    rows = []
    for g in guidance:
        actual = next((f for f in facts if f["metric"] == g.metric and f["basis"] in ("GAAP", "unspecified", "non-GAAP")
                       and ((g.unit == "percent") == (f["unit"] == "percent"))), None)
        row = asdict(g)
        if g.horizon != "quarter":
            rows.append({**row, "verdict": "not_comparable", "actual": None})
            continue
        if actual is None:
            rows.append({**row, "verdict": "no_actual", "actual": None})
            continue
        value = _to_unit(actual["value"], actual["unit"]) if g.unit != "percent" else _d(actual["value"])
        lo, hi = _d(g.low), _d(g.high)
        mid = (lo + hi) / 2
        if value > hi * (1 + tolerance_pct / 100):
            verdict = "beat"
        elif value < lo * (1 - tolerance_pct / 100):
            verdict = "miss"
        else:
            verdict = "in_line"
        surprise = (value - mid) / mid * 100 if mid else None
        rows.append({**row, "verdict": verdict, "actual": {"value": format(value.normalize(), "f"), "unit": g.unit,
                     "quote": actual["evidence"]["quote"], "page": actual["evidence"]["page"],
                     "source": actual["evidence"]["source"]},
                     "surprise_vs_midpoint_pct": str(surprise.quantize(Decimal("0.01"))) if surprise is not None else None})
    return rows


def next_period(periods: list[str], current: str) -> str | None:
    def key(p):
        q, y = p.split("-")
        return (int(y), int(q[1]))
    ordered = sorted(periods, key=key)
    i = ordered.index(current) if current in ordered else -1
    return ordered[i + 1] if 0 <= i < len(ordered) - 1 else None
