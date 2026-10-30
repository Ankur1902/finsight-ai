"""Guardrails for a financial RAG assistant.

Layered, dependency-free and deterministic so they run on every request:

  input      -> length, prompt-injection, PII redaction, out-of-coverage
                companies, personalised-investment-advice detection
  retrieval  -> period-not-covered, low-relevance abstention, poisoned-chunk
                filtering (indirect prompt injection inside documents)
  output     -> citation validity, numeric grounding (every figure in the
                answer must appear in the retrieved context), advice language,
                system-prompt leakage

Each check returns flags rather than raising, so the pipeline decides policy
and the UI / eval harness can surface exactly what fired.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from langchain_core.documents import Document

from .config import MAX_QUESTION_CHARS, MIN_RERANK_SCORE

REFUSAL_TEXT = "I couldn't find that information in the provided documents."
ADVICE_DISCLAIMER = (
    "_Finsight summarises what management said on earnings calls. It is not "
    "investment advice and does not make buy/sell recommendations._"
)

# --------------------------------------------------------------------------- #
# Shared result type
# --------------------------------------------------------------------------- #


@dataclass
class GuardrailResult:
    allowed: bool = True
    message: str | None = None  # user-facing reason when blocked
    flags: list[str] = field(default_factory=list)
    text: str = ""  # possibly rewritten text (redacted question / fixed answer)
    details: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|preceding)\s+(instructions|prompts?|rules|context)",
    r"disregard\s+(all\s+|the\s+|your\s+)?(previous|prior|above|system|instructions|rules)",
    r"forget\s+(everything|all|your)\s+(instructions|rules|above|previous)",
    r"(reveal|show|print|repeat|leak|output)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)",
    r"\bsystem\s+prompt\b",
    r"you\s+are\s+now\s+(a|an|in)\b",
    r"\b(developer|dan|god|jailbreak)\s+mode\b",
    r"\bjailbreak\b",
    r"pretend\s+(you\s+are|to\s+be)\b",
    r"act\s+as\s+(if\s+you\s+are\s+|an?\s+)?(unrestricted|unfiltered|different)",
    r"</?\s*(system|assistant|instructions?)\s*>",
    r"new\s+instructions\s*:",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.I)

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone": re.compile(r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
}

ADVICE_PATTERNS = re.compile(
    r"\b(should\s+i\s+(buy|sell|invest|hold|short)|is\s+\w+\s+a\s+(good|bad)\s+(buy|investment|stock)|"
    r"(buy|sell)\s+or\s+(sell|hold|buy)|price\s+target|will\s+(the\s+)?(stock|shares?)\s+(go|rise|fall|drop)|"
    r"how\s+much\s+should\s+i\s+invest|best\s+stock|recommend\w*\s+(a\s+)?(stock|investment)|"
    r"worth\s+investing|portfolio\s+allocation)\b",
    re.I,
)

# Companies people commonly ask about that are *not* in this corpus.
UNCOVERED_COMPANIES = re.compile(
    r"\b(apple|aapl|iphone|google|alphabet|googl|amazon|amzn|aws|tesla|tsla|netflix|nflx|"
    r"amd|intel|intc|oracle|orcl|salesforce|crm|ibm|broadcom|avgo|openai|anthropic|samsung|tsmc)\b",
    re.I,
)
COVERED_HINT = re.compile(r"\b(meta|microsoft|msft|nvidia|nvda|azure|instagram|whatsapp|facebook)\b", re.I)


def _luhn_ok(digits: str) -> bool:
    nums = [int(d) for d in digits][::-1]
    total = sum(nums[0::2]) + sum(sum(divmod(2 * d, 10)) for d in nums[1::2])
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, list[str]]:
    found: list[str] = []

    def _sub(kind: str):
        def repl(m: re.Match) -> str:
            if kind == "card":
                digits = re.sub(r"\D", "", m.group())
                if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                    return m.group()
            found.append(kind)
            return f"[REDACTED_{kind.upper()}]"

        return repl

    for kind, pattern in PII_PATTERNS.items():
        text = pattern.sub(_sub(kind), text)
    return text, sorted(set(found))


# Zero-width, bidi and other invisible format characters used to split trigger
# words ("ig\u200bnore") past regex filters.
_INVISIBLE_RE = re.compile(r"[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180e\u200b-\u200f"
                           r"\u202a-\u202e\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0]")


def normalize_text(text: str) -> str:
    """Canonical form used for *detection only* (never shown back to the user):
    NFKC folds full-width/compatibility lookalikes, invisible characters and
    control characters are removed, whitespace is collapsed."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _INVISIBLE_RE.sub("", text)
    text = "".join(c if c in "\n\t" or unicodedata.category(c)[0] != "C" else " " for c in text)
    return re.sub(r"\s+", " ", text).strip()


def is_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text) or _INJECTION_RE.search(normalize_text(text)))


def check_input(question: str) -> GuardrailResult:
    q = (question or "").strip()
    if not q:
        return GuardrailResult(False, "Please enter a question.", ["empty"], q)
    if len(q) > MAX_QUESTION_CHARS:
        return GuardrailResult(
            False,
            f"Questions are limited to {MAX_QUESTION_CHARS} characters.",
            ["too_long"],
            q[:MAX_QUESTION_CHARS],
        )

    if is_injection(q):
        return GuardrailResult(
            False,
            "That request tries to change how the assistant behaves, so I can't run it. "
            "Ask a question about the Meta, Microsoft or NVIDIA earnings calls instead.",
            ["prompt_injection"],
            q,
        )

    # Detection runs on the original *and* the normalised form so obfuscated
    # PII (full-width digits, zero-width separators) is still redacted.
    redacted, pii = redact_pii(normalize_text(q) if normalize_text(q) != q else q)
    flags = [f"pii_redacted:{kind}" for kind in pii]

    if UNCOVERED_COMPANIES.search(redacted) and not COVERED_HINT.search(redacted):
        return GuardrailResult(
            False,
            "Finsight only covers Meta, Microsoft and NVIDIA earnings calls, so I can't "
            "answer questions about other companies.",
            flags + ["out_of_coverage_company"],
            redacted,
        )

    if ADVICE_PATTERNS.search(redacted):
        flags.append("investment_advice_request")

    return GuardrailResult(True, None, flags, redacted)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #


def escape_untrusted(text: str) -> str:
    """Neutralise markup that could close or forge the prompt's <source> /
    <conversation_so_far> delimiters from inside retrieved or user text."""
    return re.sub(r"<(/?)\s*(source|sources|conversation_so_far|system|assistant|instructions?)\b",
                  lambda m: f"&lt;{m.group(1)}{m.group(2)}", text or "", flags=re.I)


def filter_poisoned_chunks(docs: list[Document]) -> tuple[list[Document], int]:
    """Drop retrieved chunks that contain instructions aimed at the model
    (indirect prompt injection). Earnings transcripts shouldn't, but user-added
    documents might."""
    clean = [d for d in docs if not is_injection(d.page_content)]
    return clean, len(docs) - len(clean)


def check_retrieval(docs: list[Document], min_score: float = MIN_RERANK_SCORE) -> GuardrailResult:
    if not docs:
        return GuardrailResult(False, REFUSAL_TEXT, ["no_documents"])
    if all(d.metadata.get("retrieval_method") == "lexical" for d in docs):
        supported = any(d.metadata.get("lexical_score", 0) > 0 and d.metadata.get("term_coverage", 0) >= 0.5 for d in docs)
        return GuardrailResult(supported, None if supported else REFUSAL_TEXT,
                              [] if supported else ["low_relevance"],
                              details={"retrieval_method": "lexical"})
    best = max(d.metadata.get("rerank_score", 0.0) for d in docs)
    if best < min_score:
        return GuardrailResult(False, REFUSAL_TEXT, ["low_relevance"], details={"best_score": best})
    return GuardrailResult(True, details={"best_score": best})


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# $65.6 billion, 33%, 3.30, 1,250 ... (years and tiny bare integers are ignored)
_NUMBER_RE = re.compile(r"(?<![\w.])\$?(-?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?))(\s*%|\s*(?:billion|million|trillion|bn|b|m)\b)?", re.I)
_ADVICE_OUT_RE = re.compile(
    r"\b(you\s+should\s+(buy|sell|invest|hold)|i\s+(would\s+)?recommend\s+(buying|selling|investing)|"
    r"(strong|a)\s+(buy|sell)\s+(rating|signal)|good\s+time\s+to\s+(buy|sell))\b",
    re.I,
)
# Fixed canary embedded in the system prompt; if it ever shows up in an answer
# the prompt has leaked (or the model was coerced into echoing it).
PROMPT_CANARY = "FNS-7c1d9e42"
_LEAK_MARKERS = ("Rules you must follow", "You are Finsight", PROMPT_CANARY)


def extract_numbers(text: str) -> list[str]:
    text = re.sub(r"-\s*\$", "$-", text.replace("−", "-"))
    text = _CITATION_RE.sub(" ", text)
    out = []
    for m in _NUMBER_RE.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").strip()
        value = raw.replace(",", "")
        if not unit and "." not in value and "$" not in m.group(0):
            n = int(value)
            if abs(n) < 10 or 1990 <= n <= 2035:  # quarter numbers, years
                continue
        out.append(value)
    return out


def _context_numbers(context: str) -> set[Decimal]:
    context = re.sub(r"-\s*\$", "$-", context.replace("−", "-"))
    return {
        Decimal(m.group(1).replace(",", "")).normalize()
        for m in re.finditer(r"(?<![\w.])\$?(-?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?))", context)
    }


def _number_in_context(value: str, context_numbers: set[Decimal]) -> bool:
    return Decimal(value).normalize() in context_numbers  # 3.3 == 3.30, 1250 == 1,250


def cited_indices(answer: str) -> list[int]:
    return [int(n) for group in _CITATION_RE.findall(answer) for n in re.split(r"\s*,\s*", group)]


def check_output(answer: str, docs: list[Document], advice_requested: bool = False) -> GuardrailResult:
    flags: list[str] = []
    text = answer.strip()
    details: dict = {}

    if any(marker in text for marker in _LEAK_MARKERS):
        return GuardrailResult(False, REFUSAL_TEXT, ["system_prompt_leak"], REFUSAL_TEXT)

    refused = REFUSAL_TEXT.lower().rstrip(".") in text.lower()
    details["refused"] = refused
    if refused:
        # Abstentions must not become successful cached answers.
        return GuardrailResult(False, text, ["model_refusal"], text, details)

    # Citations -----------------------------------------------------------
    cites = cited_indices(text)
    invalid = sorted({c for c in cites if c < 1 or c > len(docs)})
    if invalid:
        flags.append("invalid_citation")
        details["invalid_citations"] = invalid
        text = _CITATION_RE.sub(
            lambda m: "["
            + ", ".join(n for n in re.split(r"\s*,\s*", m.group(1)) if 1 <= int(n) <= len(docs))
            + "]"
            if any(1 <= int(n) <= len(docs) for n in re.split(r"\s*,\s*", m.group(1)))
            else "",
            text,
        )
    if not any(1 <= c <= len(docs) for c in cites) and not refused:
        flags.append("uncited_answer")
    details["citation_count"] = len([c for c in cites if 1 <= c <= len(docs)])

    # Numeric grounding ---------------------------------------------------
    # A number appearing in an unrelated retrieved passage is not citation support.
    cited_docs = [docs[i - 1] for i in sorted(set(cites)) if 1 <= i <= len(docs)]
    context_numbers = _context_numbers("\n".join(d.page_content for d in cited_docs))
    numbers = extract_numbers(text)
    ungrounded = [n for n in numbers if not _number_in_context(n, context_numbers)]
    details["numbers_total"] = len(numbers)
    details["numbers_ungrounded"] = ungrounded
    details["numeric_grounding"] = 1.0 if not numbers else 1 - len(ungrounded) / len(numbers)
    if ungrounded:
        flags.append("ungrounded_numbers")
    if not refused and ("uncited_answer" in flags or ungrounded):
        message = "I couldn't verify this generated answer against valid source citations. Please rephrase the question or inspect the retrieved passages."
        return GuardrailResult(False, message, flags, message, details)

    # Advice --------------------------------------------------------------
    if _ADVICE_OUT_RE.search(text):
        flags.append("advice_language")
    if advice_requested or "advice_language" in flags:
        text += "\n\n" + ADVICE_DISCLAIMER

    return GuardrailResult(True, None, flags, text, details)
