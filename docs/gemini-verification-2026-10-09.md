# Gemini verification — October 9, 2026

The preview now uses the user's locally configured Gemini key. No key is embedded
in frontend code, reports or the question manifest; `.env` is excluded from Git.
Real generation, not a fixture model, produced the results below.

## Configuration and changes

- Gemini 3.1 Flash-Lite, minimal thinking, 384 output-token budget for chat.
- Metadata-scoped BM25L retrieval over exact PDF passages, with three sources.
- Actual company-revenue statements precede high-frequency segment commentary.
- Cached, versioned PDF snapshots and startup warm-up eliminate neural loading
  from the interactive path. Existing hybrid search remains selectable.
- A bounded ten-minute cache stores validated, warning-free replies without
  feedback capabilities. Each response is separately registered for feedback.
- Hosted chat does not queue behind local inference/analytics locking.
- Financial results are extracted in one structured generation request per period.
  Gemini receives a compatible structural grammar; Pydantic continues to enforce
  values, units, quote lengths, extra-field rejection and evidence provenance.
- Quarterly narrative context is balanced across guidance, risk, investment and
  business themes. Unsupported quotes/categories increment extraction issues.
- The frontend selects the answer's first cited source, labels cached replies and
  displays only benchmark-passing examples for the current configuration.

## Repeated uncached question checks

Each question was run three times after warm-up. Checks required the gold answer,
valid citations, correct company/fiscal-period source metadata, no guardrail
failures and no unsupported figures. Actual supporting passages were reviewed.

| Question | Validated answer | Observed completion range | Fast shortcut |
| --- | --- | --- | --- |
| What was Microsoft's revenue for FY25 Q1? | $65.6 billion | 0.93–7.10 s | No; timing outlier |
| What was Microsoft's earnings per share in FY25 Q1? | $3.30 | 1.15–7.95 s | No; timing outlier |
| What was Meta's total revenue in Q1 2025? | $42.3 billion | 0.90–6.15 s | No; timing outlier |
| What was Microsoft Cloud revenue in FY25 Q1 and how much did it grow? | $38.9 billion; 22% growth | 0.96–1.18 s | Yes; all three checks passed |

These are a small observed sample, not a statistical p95 claim or a guarantee of
perfect future answers. Only the last question is published in the frontend.
The manifest expires automatically when relevant corpus/model/prompt/retrieval
settings change. Raw records are in `.e2e/gemini-final-verification.json`.

## Real frontend-to-backend HTTP checks

Measured through the running Next.js API proxy:

| Operation | Observed time |
| --- | --- |
| New Microsoft Cloud answer | 2.50 s in the final HTTP run |
| Same answer from validated reply cache | 0.29 s |
| Fresh Meta Q1 2025 metric extraction | 2.11 s |
| Cached metric extraction | 0.24 s |
| Initial Meta Q1→Q2 quarterly comparison | 5.79 s |
| Cached quarterly comparison | 0.42 s |

After balanced narrative extraction was added, a run concurrent with the
production build measured 17.60 seconds for the fresh two-finding comparison and
4.97 seconds for its cached response. Those values do not meet a universal
five-second promise. After the build finished and cache reads were moved outside
the generation lock, the same validated cached comparison measured 0.39–0.53
seconds. A repeated cached metric request measured 0.73 seconds (the first after
restart measured 2.54 seconds). The records are in
`.e2e/gemini-quiet-cache-verification.json`.

Earlier chat HTTP checks measured 1.14–1.41 seconds for new answers. Warm lexical
retrieval usually took tens of milliseconds, compared with roughly 23 seconds
in the previous CPU hybrid run. Cold process initialization still takes longer
and occurs before the Gemini backend reports readiness.

The actual Meta results included Q1 revenue $42.3B, operating margin 41%, capex
$13.7B; Q2 revenue $47.5B, margin 43%, capex $17B. Computed changes are $5.2B revenue,
2 percentage points operating margin and $3.3B capex. One proposed Q2 fact failed
validation and was withheld. Missing metrics were not fabricated.

The improved narrative context additionally yielded two validated guidance
comparisons: 2026 investment outlook and narrowing 2025 expense guidance. Both
include exact quotations from the respective calls. That separate process run
included cold initialization and fresh extraction for both periods; it is not
evidence of a five-second cold-start narrative response. Records are in
`.e2e/gemini-narrative-verification.json`.

## Browser and regressions

The real browser displays the approved question, generated answer, cached-reply
label and Microsoft Cloud source at page 16. The source passage states $38.9B
and 22%. Financial cards use the real Gemini extraction, including withheld-fact
notices. Screenshots are stored under `.e2e/screenshots/`.

The complete backend regression run passed 77 tests, including real corpus
ingestion. After the cache-concurrency regression was added, the final lightweight
run passed 77 tests with that unchanged corpus test excluded; focused provider
and analyst checks were also repeated.
All 15 frontend tests, TypeScript checks, formatting and production build pass.
A Pydantic field-metadata warning remains in one API test; it did not fail tests.

## Remaining limits

New Gemini replies can exceed five seconds due to provider/network variation.
The data does not justify promising every fresh answer under five seconds.
Cached replies and precomputed analytics are the more predictable fast path.
Fast lexical retrieval can miss semantic paraphrases; hybrid mode is available
for broader recall evaluation. These four questions do not validate all companies,
periods, narrative interpretations or concurrency levels. Keep inspecting evidence.
