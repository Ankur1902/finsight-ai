from src.eval import redteam


def test_gated_asr_is_zero_and_hardening_helps():
    result = redteam.run()
    assert result["gated_asr"] == 0.0, result["categories"]
    assert result["hardened_asr"] < result["baseline_asr"]


def test_known_gaps_stay_documented():
    cats = redteam.run()["categories"]
    assert cats["injection_known_gap"]["hardened_asr"] > 0  # remove the case when a defence lands


def test_groundedness_golden_set():
    from src.eval.ci_gate import groundedness
    assert groundedness()["wrong"] == []
