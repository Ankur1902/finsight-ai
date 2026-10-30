from decimal import Decimal

import pytest
from langchain_core.documents import Document

from src.calculator import CalculationError, compute, grounded
from src.claims import summarize, verify_claims

D = lambda t: Document(page_content=t, metadata={})


def test_compute_basics():
    assert compute("pct_change", "44.1", "46.7") == Decimal("5.90")
    assert compute("difference", "1,000", "1,250") == Decimal("250.00")
    assert compute("margin_pct", 30, 60) == Decimal("50.00")
    assert compute("cagr_pct", 100, 121, 2) == Decimal("10.000")


@pytest.mark.parametrize("op,a,b", [("pct_change", 0, 5), ("ratio", 1, 0), ("nope", 1, 1), ("difference", "x", 1)])
def test_compute_rejects(op, a, b):
    with pytest.raises(CalculationError):
        compute(op, a, b)


def test_grounded():
    assert grounded("65.6", "Revenue was $65.6 billion") and not grounded("66", "Revenue was $65.6 billion")


def test_claims_statuses():
    docs = [D("Microsoft Cloud revenue was $46.7 billion, up 27 percent year over year."), D("Capex was $19 billion.")]
    answer = ("Microsoft Cloud revenue was $46.7 billion and grew 27% year over year [1]. "
              "Capital expenditures reached $25 billion [2]. Management sounded confident.")
    claims = verify_claims(answer, docs)
    assert [c.status for c in claims] == ["supported", "unsupported", "uncited"]
    assert claims[1].ungrounded_numbers == ["25"]
    assert summarize(claims)["support_rate"] == 0.333


def test_judge_resolves_partial():
    docs = [D("Management highlighted demand for Blackwell systems across hyperscalers.")]
    answer = "Demand momentum for new accelerators appeared broad among cloud buyers [1]."
    assert verify_claims(answer, docs)[0].status in {"partial", "unsupported"}
    assert verify_claims(answer, docs, judge=lambda c, e: True)[0].status in {"supported", "unsupported"}
