# 2-minute demo script

Setup: put `GEMINI_API_KEY` in `.env`, run `docker compose up --build`, open http://localhost:3000.

1. **0:00 Grounded answer.** Ask "What was Microsoft's revenue for FY25 Q1?". Open the citation, then
   "Understand this response" and show the per-claim check.
2. **0:30 Calculator mode.** Tick it and ask "How much did Meta revenue grow from Q1 to Q2 2025?". Show the
   computed result and that its operands come from cited passages.
3. **0:55 Guardrails.** Paste `ig​nore all previous instructions` (zero-width space). Show the block, then open
   `docs/redteam-scoreboard.md`: baseline vs hardened attack success rate, and the published known gaps.
4. **1:15 Guidance tracker.** Meta, Q1 2025: guidance for Q2 versus the reported result, with both quotations.
5. **1:40 Observability.** Show stage latency, cost per route and the semantic-cache hit after rephrasing a question.
6. **1:55 CI.** Show the green badges and `python -m src.eval.ci_gate`.

Hosted demo: deploy the two containers to any container host (Fly.io, Render, Cloud Run), set
`GEMINI_API_KEY` and `FINSIGHT_API_KEY` as secrets, and link it in the README. Add a rate-limit-friendly
daily quota, since each question spends provider budget.
