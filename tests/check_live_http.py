"""Read-only proxy boundary smoke checks against an explicitly selected test URL."""
import argparse
import json
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Isolated frontend base URL")
    args = parser.parse_args()
    base = args.base.rstrip("/") + "/api/"
    results = []
    cases = [
        ("metrics?company=unknown&period=Q1-2025", None, None, 422),
        ("documents/missing.pdf", None, None, 404),
        ("chat/extra", None, None, 404),
        ("chat", None, None, 405),
        ("feedback", b"{}", "text/plain", 415),
        ("feedback", b"x" * 262145, "application/json", 413),
    ]
    for route, body, content_type, expected in cases:
        request = urllib.request.Request(base + route, data=body,
            headers={"Content-Type": content_type} if content_type else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        assert status == expected, (route, expected, status)
        results.append({"route": route, "status": status, "expected": expected})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
