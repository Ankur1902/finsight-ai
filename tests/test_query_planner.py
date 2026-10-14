from src.query_planner import Target, detect_companies, detect_periods, plan_query

CATALOG = {
    "microsoft": [("Q1", "2025"), ("Q2", "2025"), ("Q3", "2025"), ("Q4", "2025")],
    "meta": [("Q1", "2025"), ("Q2", "2025"), ("Q3", "2025")],
    "nvda": [("Q1", "2026"), ("Q2", "2026")],
}


def test_company_detection_uses_word_boundaries():
    assert detect_companies("What is the metadata schema?") == []
    assert detect_companies("Meta and NVDA results") == ["meta", "nvda"]
    assert detect_companies("How did Azure grow?") == ["microsoft"]  # product hint


def test_period_formats():
    assert detect_periods("FY25 Q1 revenue") == [("Q1", "2025")]
    assert detect_periods("Q1 fiscal 2026") == [("Q1", "2026")]
    assert detect_periods("the first quarter of 2025") == [("Q1", "2025")]
    assert detect_periods("Q3 2025 vs Q2 2025") == [("Q3", "2025"), ("Q2", "2025")]
    assert detect_periods("full year fiscal 2026") == [(None, "2026")]


def test_latest_resolves_from_catalog():
    plan = plan_query("Meta's latest capex outlook", CATALOG)
    assert plan.targets == [Target("meta", "Q3", "2025")]


def test_trend_expands_to_each_quarter():
    plan = plan_query("How has Microsoft revenue trended?", CATALOG)
    assert plan.is_comparison and len(plan.targets) == 4


def test_cross_company_comparison():
    plan = plan_query("Compare Meta and Microsoft capex in the latest quarter", CATALOG)
    assert set(plan.targets) == {Target("meta", "Q3", "2025"), Target("microsoft", "Q4", "2025")}


def test_follow_up_inherits_company_and_period():
    first = plan_query("What was Meta revenue in Q2 2025?", CATALOG)
    follow = plan_query("And what about their capex?", CATALOG, first)
    assert follow.inherited and follow.targets == [Target("meta", "Q2", "2025")]


def test_standalone_question_does_not_inherit():
    first = plan_query("What was Meta revenue in Q2 2025?", CATALOG)
    new = plan_query("Who is NVIDIA's CFO?", CATALOG, first)
    assert not new.inherited and new.targets == [Target("nvda")]


def test_company_period_pairs_do_not_form_cartesian_product():
    plan = plan_query("Compare NVIDIA Q1 fiscal 2026 revenue with Meta Q1 2025 revenue", CATALOG)
    assert set(plan.targets) == {Target("nvda", "Q1", "2026"), Target("meta", "Q1", "2025")}


def test_guidance_year_does_not_change_reporting_period():
    plan = plan_query("What was Meta revenue in Q4 2025 and its 2026 capex guidance?", CATALOG)
    assert plan.targets == [Target("meta", "Q4", "2025")]
