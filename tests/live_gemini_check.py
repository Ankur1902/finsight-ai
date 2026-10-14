"""Manual end-to-end check against the user's running frontend. Uses real Gemini.

Do not run without approval to use the locally configured provider key.
Output intentionally omits feedback tokens.
"""
import json
from pathlib import Path
import time
import urllib.request


def request(path, body=None):
    req = urllib.request.Request("http://127.0.0.1:13000/api/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.load(response)
    return result, round((time.perf_counter() - t) * 1000, 2)


if __name__ == "__main__":
    report = {}
    questions, ms = request("questions")
    report["questions"] = questions
    print("Published questions:", len(questions["questions"]), "HTTP ms:", ms, flush=True)
    query = "What was Microsoft Cloud revenue in FY25 Q1 and how much did it grow?"
    replies = []
    for _ in range(2):
        result, ms = request("chat", {"question": query, "history": []})
        assert not result["blocked"] and "38.9" in result["answer"] and "22" in result["answer"]
        replies.append({k: result[k] for k in ("answer", "sources", "model", "cached", "timings_ms")})
        replies[-1]["http_ms"] = ms
        print("Chat HTTP ms:", ms, "cached:", result["cached"], "answer:", result["answer"], flush=True)
    assert replies[1]["cached"]
    report["chat"] = replies
    metrics, ms = request("metrics?company=meta&period=Q1-2025")
    assert any(f["metric"] == "revenue" and f["value"] == 42.3 for f in metrics["facts"])
    report["metrics"] = {"http_ms": ms, "result": metrics}
    print("Metrics HTTP ms:", ms, "facts:", [(f["metric"], f["value"]) for f in metrics["facts"]], flush=True)
    cached_metrics, ms = request("metrics?company=meta&period=Q1-2025")
    assert cached_metrics["facts"] == metrics["facts"]
    report["cached_metrics_ms"] = ms
    print("Cached metrics HTTP ms:", ms, flush=True)
    output = Path(".e2e/gemini-http-verification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
