import json
from datetime import datetime, timezone
from src.questions import verified_questions


def test_only_current_passing_questions_are_served(monkeypatch, tmp_path):
    monkeypatch.setattr("src.questions.ROOT_DIR", tmp_path)
    monkeypatch.setattr("src.questions.configuration_fingerprint", lambda: "current")
    path = tmp_path / "verified_questions.json"
    assert verified_questions() == {"questions": []}
    data = {"configuration": "current", "checked_at": datetime.now(timezone.utc).isoformat(),
            "questions": [{"id": "revenue", "question": "Revenue?", "max_ms": 1000, "runs": 3}]}
    path.write_text(json.dumps(data))
    assert len(verified_questions()["questions"]) == 1
    data["configuration"] = "old"
    path.write_text(json.dumps(data))
    assert verified_questions() == {"questions": []}
    data["configuration"] = "current"
    data["questions"][0]["max_ms"] = 5001
    path.write_text(json.dumps(data))
    assert verified_questions() == {"questions": []}


def test_malformed_and_expired_manifests_are_hidden(monkeypatch, tmp_path):
    monkeypatch.setattr("src.questions.ROOT_DIR", tmp_path)
    monkeypatch.setattr("src.questions.configuration_fingerprint", lambda: "current")
    path = tmp_path / "verified_questions.json"
    for report in [[], None, "invalid", {"configuration": "current", "checked_at": "2020-01-01T00:00:00+00:00", "questions": []},
                   {"configuration": "current", "checked_at": None, "questions": []}]:
        path.write_text(json.dumps(report))
        assert verified_questions() == {"questions": []}
