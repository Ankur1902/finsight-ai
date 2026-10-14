# Upgrade plan: complete answers within five seconds

**October 9 update:** Gemini integration, fast lexical retrieval, corpus warm-up,
batched financial extraction and a validated answer cache are implemented. The
project-root `.env` currently selects Gemini 3.1 Flash-Lite with minimal thinking.
See [actual measurements](gemini-verification-2026-10-09.md). The older Anthropic
steps below remain an alternative, rather than the current preview configuration.

The current CPU pipeline does not meet this target. The latest recorded real
Microsoft revenue request took 92.3 seconds: retrieval 23.2 seconds, generation
54.6 seconds, and additional initialization/processing time. It was withheld
because the model did not supply valid citations. A smaller output budget alone
cannot resolve the retrieval bottleneck or financial accuracy.

## 1. Change generation compute

The existing backend supports Anthropic. Start with a model available to your
account and benchmark it on the financial reference cases. For example, the
documented Claude Sonnet 5.5 model supports low effort. API usage is billable.

Set these in the PowerShell terminal used to start the backend. Obtain the API
key in your provider account and set it locally; do not put it in frontend code,
Git, or a chat message.

```powershell
$env:ANTHROPIC_API_KEY = '<your API key>'
$env:FINSIGHT_LLM_PROVIDER = 'anthropic'
$env:FINSIGHT_ANTHROPIC_MODEL = 'claude-sonnet-5-5'
$env:FINSIGHT_ANTHROPIC_EFFORT = 'low'
$env:FINSIGHT_MAX_NEW_TOKENS = '192'
.venv/Scripts/python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 18000
```

Stop the previous Finsight backend first, then restart it with these settings.
The hosted chat generator now honors `FINSIGHT_MAX_NEW_TOKENS`; extraction still
uses its explicit, larger JSON budget. Benchmark shorter answers for truncation
and citation completeness before accepting this setting. Provider changes are
not a five-second guarantee.

For local generation, use a GPU and a serving engine appropriate for that GPU
and model. Keep generation, embedding and reranking models warm. Select hardware
based on measured model memory needs and concurrency; CPU free-tier hosting is
not evidence of meeting a latency target.

## 2. Fix retrieval latency

- Move query embeddings and reranking to accelerated or hosted inference.
- Alternatively evaluate a smaller embedding model and reranker. Changing the
  embedding model requires rebuilding a separate index; never query existing
  bge-m3 vectors with another embedding space, even if dimensions happen to match.
- Reduce candidate reranking and context length only after testing retrieval
  recall, fiscal-period coverage and consolidated-versus-segment attribution.
- Warm model/index initialization before accepting traffic. Track cold starts
  separately; they are still part of the visitor's observed wait.
- Keep slow dashboard extraction out of the interactive chat queue. The current
  shared inference lock serializes these operations; generation provider changes
  alone do not remove time waiting behind another request.

## 3. Precompute dashboard results and approved answers

Extract metrics and quarterly findings offline, review their source quotes,
units, accounting bases, scope and periods, and serve approved results from
persistent storage. For common questions, a reviewed answer cache is the most
predictable route to a fast response. This serves an existing answer; it does
not perform new generation in under five seconds.

Key cached answers by question/scope, corpus fingerprint, model and prompt
version. Invalidate them when these change, preserve citations, label cached
results and register a new feedback capability for each delivered reply. Prompt
caching is different: it reuses provider-side input processing, not completed
answers. Streaming improves time to first text, not necessarily completion time.

## 4. Verify the five-second target and question shortcuts

Measure end-to-end completion time from browser submission to the final validated
answer, including queueing, retrieval, provider network time and output checks.
Run repeated cold/warm and concurrent tests; accept a target such as p95 below
five seconds for an explicitly defined workload, rather than relying on one run.

Use `src/eval/cases.json` as candidate reference cases, not as a list of passed
questions. Check every proposed shortcut against the real provider and corpus:

1. Correct company, fiscal quarter, total/segment scope, unit and accounting basis.
2. Exact figure or defensible interpretation, checked against the original PDF.
3. Valid citations attached to the supporting passages.
4. No refusal, unsupported figures, truncated output or extraction failures.
5. Repeated completion times within the target.

Record the corpus/model/prompt versions, approved answer and evidence, review
date and measured times. Display only approved cases and invalidate approval
after relevant changes. This is evidence of passing a defined benchmark, not a
promise that generative output will always be perfect.

The four unverified frontend shortcuts were removed. One real-Gemini question now
passes repeated correctness/citation/timing checks and is published through the
configuration-bound `verified_questions.json` manifest. Deterministic UI fixtures
from the earlier browser tests do not qualify as successful AI generation.

## Primary documentation

- [Claude latency guidance](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)
- [Claude effort controls](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Claude prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Hugging Face GPU serving and inference optimizations](https://huggingface.co/docs/text-generation-inference/index)
