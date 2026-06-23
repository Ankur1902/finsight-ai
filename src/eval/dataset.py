import json
from pathlib import Path

EVAL_CASES = json.loads(
    (Path(__file__).with_name("cases.json")).read_text(encoding="utf-8")
)
