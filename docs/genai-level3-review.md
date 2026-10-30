# GenAI Level 3 review, hardening and portfolio ideas

"Level 3" is read here as a production-grade RAG/GenAI system: grounded, evaluated,
guarded, observable and resilient.

## 1. Review

**Strong (already above typical Level 3)**
- Layered guardrails (input, retrieval, output) with flags rather than exceptions.
- Numeric grounding: every figure in an answer must appear in a *cited* passage.
- Abstention on weak retrieval; fiscal-period coverage checks; query planner for follow-ups.
- Indirect prompt-injection filtering of retrieved chunks; PII redaction; Luhn check.
- Multi-provider LLM abstraction (local, Gemini, Anthropic) with sanitized provider errors.
- Evaluation harness (retrieval metrics, RAGAS, verified-question manifest), feedback loop,
  bounded request bodies, 104 offline tests.

**Gaps found**
| Area | Finding | Status |
|---|---|---|
| AI security | Injection/PII regexes bypassed by zero-width or full-width characters | Fixed (`normalize_text`) |
| AI security | Retrieved text could close `</source>` and forge sources/instructions | Fixed (`escape_untrusted`) |
| AI security | Prompt-leak check relied on two phrases | Fixed (canary token) |
| Resilience | No retry/backoff for 429/5xx/timeouts; local model errors unwrapped | Fixed (`with_retries`) |
| Abuse/cost | No rate limiting or auth on paid-model endpoints (denial of wallet) | Fixed (`security.py`, optional `FINSIGHT_API_KEY`) |
| Hardening | No security headers / request IDs; warm-up failure would crash startup | Fixed |
| Remaining | Regex injection detection is English-only and heuristic; add a classifier or LLM judge | Open |
| Remaining | Rate limiter is in-process (use Redis for multi-worker); README still describes a Streamlit `app.py` that no longer exists; trace log has no rotation; no CI workflow | Open |

## 2. Changes made
`src/guardrails.py`, `src/prompts.py`, `src/errors.py`, `src/llm.py`, `src/api.py`,
new `src/security.py`, proxy route key/IP forwarding, `tests/test_security.py`.

## 3. Ideas to make the portfolio piece distinctive
1. **Public red-team benchmark**: ship an adversarial suite (obfuscated injections, poisoned PDFs,
   unit/fiscal-period traps) with a scoreboard in the README: attack success rate before/after each guardrail.
2. **Claim-level verification**: split the answer into atomic claims and check each against its
   cited span (NLI or LLM judge); show a per-sentence "supported / unsupported" UI.
3. **Cross-quarter contradiction and guidance-vs-actual tracker**: auto-detect where management's
   prior guidance differed from reported results, with quotes and pages.
4. **Observability**: OpenTelemetry/Langfuse traces, cost and latency per stage, a live dashboard.
5. **Eval in CI**: GitHub Action running offline tests plus a small golden-set regression that fails
   on groundedness or hit-rate drops; publish the badge.
6. **Semantic cache and model router**: route easy lookups to a cheap model, hard comparisons to a
   stronger one; report cost per correct answer.
7. **Agentic mode with tool use**: a calculator/XBRL tool for growth rates so numbers are computed, not generated.
8. **One-command demo**: Docker compose plus a hosted demo and a 2-minute video.
