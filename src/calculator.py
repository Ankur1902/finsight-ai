"""Deterministic financial arithmetic. Python Decimal does the maths so the
model never has to; operands must be grounded in cited source text."""
from __future__ import annotations

import re
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext

getcontext().prec = 28

OPS = {
    "difference": ("b - a", 2),
    "pct_change": ("(b - a) / |a| * 100", 2),
    "ratio": ("a / b", 2),
    "margin_pct": ("a / b * 100", 2),
    "cagr_pct": ("((b / a) ** (1 / periods) - 1) * 100", 3),
    "pp_change": ("b - a (percentage points)", 2),
}


class CalculationError(ValueError):
    pass


def _dec(value) -> Decimal:
    try:
        d = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        raise CalculationError(f"Not a number: {value!r}") from None
    if not d.is_finite():
        raise CalculationError("Operands must be finite")
    return d


def compute(op: str, a, b, periods=None) -> Decimal:
    if op not in OPS:
        raise CalculationError(f"Unknown operation: {op}")
    x, y = _dec(a), _dec(b)
    try:
        if op in ("difference", "pp_change"):
            r = y - x
        elif op == "pct_change":
            if x <= 0:
                raise CalculationError("Relative change is undefined for a non-positive baseline")
            r = (y - x) / x * 100
        elif op == "ratio":
            r = x / y
        elif op == "margin_pct":
            r = x / y * 100
        else:  # cagr_pct
            n = _dec(periods)
            if x <= 0 or y <= 0 or n <= 0:
                raise CalculationError("CAGR needs positive start, end and period count")
            r = (y / x) ** (1 / n) - 1
            r *= 100
    except (DivisionByZero, InvalidOperation):
        raise CalculationError("Division by zero") from None
    return r.quantize(Decimal(1).scaleb(-OPS[op][1]))


_NUM = re.compile(r"(?<![\w.])\$?(-?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?))")


def numbers_in(text: str) -> set[Decimal]:
    return {Decimal(m.group(1).replace(",", "")).normalize() for m in _NUM.finditer(text)}


def grounded(value, source_text: str) -> bool:
    try:
        return _dec(value).normalize() in numbers_in(source_text)
    except CalculationError:
        return False


def format_result(op: str, a, b, result: Decimal) -> str:
    unit = "%" if op in ("pct_change", "margin_pct", "cagr_pct") else (" pp" if op == "pp_change" else "")
    return f"{op}({a}, {b}) = {result}{unit}  [{OPS[op][0]}]"
