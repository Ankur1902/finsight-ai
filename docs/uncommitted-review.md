# Uncommitted code review and validation plan

Date: October 11, 2026. This inventory covers the previously generated uncommitted implementation plus the current hardening changes. Files were inspected and edited; no project execution or tests were performed. Previously running services may still serve older source/builds.

## Source inventory

| Area | Files | Purpose/status |
| --- | --- | --- |
| Configuration/providers | `config.py`, `llm.py`, `errors.py`, `runtime.py`, `.env.example`, `requirements.txt` | Provider selection, bounded calls, validated settings, safe errors and local inference lock. Python dependency locking remains future work. |
| Corpus/index | `ingest.py`, `chunking.py`, `corpus.py`, `embeddings.py`, `vectorstore.py` | Header metadata, page citations, deterministic chunks and shared snapshots. Changing-file detection added; live hybrid replacement still needs atomic activation. |
| Retrieval/RAG | `query_planner.py`, `retrieval.py`, `lexical_retriever.py`, `hybrid_retriever.py`, `prompts.py`, `guardrails.py`, `rag.py`, `chat.py`, `answer_cache.py` | Scoped retrieval, evidence checks, bounded history, signed figures, refusal handling and validated-answer cache. Semantic correctness remains a limitation. |
| Financial analysis | `analytics.py` | Batch extraction, exact quotations, diluted EPS support, compatible Decimal calculations, paired narrative evidence, strict JSON and best-effort cache handling. |
| API/review storage | `api.py`, `http_boundary.py`, `feedback.py`, `eval/feedback_report.py` | Request validation without input echo, direct body limits/deadlines, safe failures, source-bound feedback, idempotent receipts and aggregates. |
| Verification/evaluation | `questions.py`, `verification.py`, `eval/verify_questions.py`, `verified_questions.json`, `eval/cases.json`, `eval/metrics.py`, `eval/run_eval.py`, `eval/ragas_eval.py` | Gold checks, source/config fingerprints, manifest expiry, configured retrieval and sanitized judge errors. Historical examples preserved but not republished. |
| Legacy interface | `app.py` | Streamlit retained with shared retrieval/examples and safe generation failure handling. Next.js remains primary. |
| Frontend shell | `frontend/app/page.tsx`, `layout.tsx`, `globals.css` | Workspace/navigation/design. Existing close-button removal preserved. |
| Research/evidence | Components `research-chat.tsx`, `citation-answer.tsx`, `answer-assessment.tsx`, `evidence.tsx`; helpers `citations.ts`, `chat.ts` | Safe answer display, valid citations, source selection, excerpt/PDF links, cancellation, export and refusal notices. |
| Feedback UI | `answer-feedback.tsx` | Rating/category/note/source selection, retries, edit state and answer capabilities. |
| Finance UI | `financial-dashboard.tsx`, `quarterly-analyst.tsx`, `financial-charts.tsx`, `use-analytics-workspace.ts`, helpers `finance.ts`, `contracts.ts`, `types.ts` | Accessible evidence-backed charts, fiscal spacing, units/basis/scope separation and stale-result checks. |
| Frontend HTTP | `frontend/lib/api.ts`, `frontend/app/api/[...path]/route.ts` | Explicit deadlines, caller cancellation, safe network errors, allowlisted routes, size limits and backend/document checks. |
| Tooling/docs/assets | Frontend package/lockfile/TypeScript configuration/type declarations, `README.md`, `docs/`, `assests/dashboard.png` | Existing setup/assets retained. Asset directory spelling preserved to avoid unrelated moves. |

Python module names above are under `src/` unless a different path is stated; frontend component/helper names refer to their existing `frontend/app/components`, `frontend/app/hooks` and `frontend/lib` directories.

## Stateful and generated changes

The initial working tree also contained modified tracked bytecode under `src/__pycache__` and `src/eval/__pycache__`, a modified `db/chroma.sqlite3`, and deleted tracked HNSW files under `db/76e9cc31-0ea3-451d-a5ac-6dcee11ade60/`.

These are existing runtime artifacts. They were not restored, regenerated, deleted, staged or committed in this review. `.gitignore` prevents new matching files from being added but does not untrack committed files. Decide separately whether to remove these artifacts from Git tracking or retain a reproducible complete index snapshot; do not accidentally include a partially replaced index in a source commit.

Ignored `.env`, frontend `.env.local`, `.e2e` reports/screenshots, local analytics/feedback SQLite files, `.next`, dependency directories and virtual environments remain separate from source. No credential file was read or printed in this review.

## Regression cases written, not executed

| Risk | Test code |
| --- | --- |
| Provider status/privacy | New `tests/test_errors.py`; hosted client fixture updated in `test_llm.py` |
| Input echo and direct backend limits | `test_api.py`: token/note privacy, safe provider 429, oversized JSON |
| Chunked/slow uploads and disconnect | New `test_http_boundary.py`: replay, size limit without Content-Length, media type, disconnect, absolute upload deadline |
| Ambiguous model JSON | `test_analytics.py`: duplicate keys, NaN/Infinity, array/null roots |
| EPS and storage failures | `test_analytics.py`: explicit diluted qualifier, unavailable cache path, corrupt row fallback |
| Financial signs/refusals | `test_guardrails.py`: positive vs negative evidence, Unicode minus, blocked refusal |
| Cache/corpus lifecycle | `test_fast_retrieval.py`: invalid bounds and repeatedly changing corpus |
| Manifest validity | `test_questions.py`: current pass, stale config, slow row, malformed/expired/missing-date manifest |
| Browser request errors | `frontend/tests/citations.test.cjs`: deadline, abort identity and transport error sanitization |

Existing ingestion, query planner, chat, feedback, chart/citation and analytics tests remain part of the later regression run. Historical test counts are not results for these latest edits.

## Later validation plan, when execution is authorized

1. Run the full backend suite with isolated storage, including the new HTTP/cache/corpus cases.
2. Run frontend tests, TypeScript, formatter checks and production build.
3. Start the project and verify contracts through both the proxy and direct backend, including failure paths.
4. Check chat citations/PDF links, source-bound feedback and retries/edits, cancellation, company/period changes, chart evidence and mobile layout.
5. Repeat real-provider uncached gold cases; record fresh/cached timing separately and republish only passing examples for the current fingerprint.
6. Simulate provider failures using doubles; do not deliberately exhaust the user's quota or expose their key.

No new passing-test claim, screenshot, benchmark, deployment or commit is made here. [Engineering decisions](engineering-decisions.md) explains the challenges, choices and limitations.
