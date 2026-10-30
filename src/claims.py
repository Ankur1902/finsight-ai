"""Claim-level verification: split an answer into atomic claims and check each
against the passages it cites. Deterministic by default; a judge callable
(e.g. an LLM/NLI model) can be injected to refine 'partial' verdicts."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Callable

from langchain_core.documents import Document

from .guardrails import _CITATION_RE, _context_numbers, extract_numbers, cited_indices

_STOP = set("""a an and are as at be been but by for from had has have in into is it its of on or that the their
they this to was were which with we our up out new also about over more than not will would can could""".split())
# Split after sentence-ending punctuation or after a trailing citation, but never between
# a period and its citation ("... basis. [1]").
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z$\d])|(?<=\])\s+(?=[A-Z$])|\n+")


@dataclass
class Claim:
    text: str
    citations: list[int]
    status: str  # supported | partial | unsupported | uncited
    support: float = 0.0
    ungrounded_numbers: list[str] = field(default_factory=list)


def split_claims(answer: str) -> list[str]:
    body = answer.split("\n\n_", 1)[0]  # drop appended disclaimers/notes
    parts = []
    for line in _SENT.split(body):
        line = re.sub(r"^[\s>*\-•|#]+", "", line).strip()
        if len(line) > 12 and re.search(r"[A-Za-z]", line) and not line.startswith("|---"):
            parts.append(line)
    return parts


def _terms(text: str) -> set[str]:
    text = _CITATION_RE.sub(" ", text.lower())
    return {t for t in re.findall(r"[a-z][a-z\-]{2,}", text) if t not in _STOP}


def verify_claims(answer: str, docs: list[Document], judge: Callable[[str, str], bool] | None = None,
                  extra_numbers: set[Decimal] | None = None) -> list[Claim]:
    out: list[Claim] = []
    for text in split_claims(answer):
        cites = [c for c in dict.fromkeys(cited_indices(text)) if 1 <= c <= len(docs)]
        if not cites:
            out.append(Claim(text, [], "uncited"))
            continue
        evidence = "\n".join(docs[c - 1].page_content for c in cites)
        nums = _context_numbers(evidence) | (extra_numbers or set())
        bad = [n for n in extract_numbers(text) if Decimal(n).normalize() not in nums]
        terms = _terms(text)
        ev_terms = _terms(evidence)
        support = len(terms & ev_terms) / len(terms) if terms else 1.0
        computed = bool(extra_numbers) and any(Decimal(n).normalize() in extra_numbers for n in extract_numbers(text))
        if bad:
            status = "unsupported"
        elif computed:
            status = "supported"  # figures were computed by the calculator from the cited operands
        elif support >= 0.6:
            status = "supported"
        elif support >= 0.35:
            status = "partial"
        else:
            status = "unsupported"
        if judge and status == "partial":
            status = "supported" if judge(_CITATION_RE.sub("", text).strip(), evidence) else "unsupported"
        out.append(Claim(text, cites, status, round(support, 2), bad))
    return out


def summarize(claims: list[Claim]) -> dict:
    total = len(claims)
    counts = {s: sum(c.status == s for c in claims) for s in ("supported", "partial", "unsupported", "uncited")}
    return {"total": total, **counts,
            "support_rate": round(counts["supported"] / total, 3) if total else 1.0}


def claims_as_dicts(claims: list[Claim]) -> list[dict]:
    return [asdict(c) for c in claims]
