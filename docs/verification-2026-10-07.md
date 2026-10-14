# Verification — October 7, 2026

**Verdict:** regression checks and controlled browser integration pass. The live
local AI configuration does not pass end-to-end financial accuracy and latency
requirements. Do not treat fixture screenshots as evidence of successful AI.

## Environment and isolation

Windows, Python 3.11, Node 24.18, Next.js 16.3.8. Local inference used offline
Qwen/Qwen2.5-0.5B-Instruct, BAAI/bge-m3 and the configured MiniLM reranker, with
two CPU threads. No Anthropic API key was configured. Available physical memory
was approximately 1.1 GB during inference on a 16 GB machine.

Existing Docker services were left running. Native tests used frontend/API ports
13000/18000; fixture tests used 13001/18001, all bound to loopback. The vector
index was copied to `.e2e/db`; analytics, feedback and traces used separate paths
under `.e2e`. Test services were stopped after verification.

## Automated checks

| Check | Result |
| --- | --- |
| `python -m pytest tests -q` | 66 passed, including actual PDF ingestion and deterministic chunking |
| Frontend `npm test` | 14 passed, including native Node fetch/Undici compatibility |
| `npm run typecheck` | Passed |
| `npm run build` | Production build passed |
| `npm run format:check` | Passed |

Live HTTP boundary checks returned the expected 422 for an invalid company,
404 for missing PDFs and nested unknown routes, 405 for GET chat, 415 for
non-JSON feedback and 413 for an oversized feedback body.

## Browser checks

Actual backend: catalog coverage loaded 17 company/period entries; PDF proxy
returned application/pdf and `%PDF-` bytes. Prompt injection was refused without
model generation. The 1,000-character question limit disabled submission.
Feedback on the refusal saved and was independently confirmed in SQLite.

Controlled model fixtures: the production Next.js frontend exercised the real
analytics validation, comparison math, PDF routes and feedback storage. Chat
answers were explicitly labeled as UI fixtures. Verified interactions:

- Numbered citations reopen the selected source, with the correct PDF page link.
- Feedback categories and attached source IDs save to SQLite; a saved receipt appears.
- The plain-language control prepares the grounded follow-up question.
- Meta Q1/Q2 2025 revenue cards display $42.3B/$47.5B; capex $13.7B/$17B.
- Historical charts show both periods; selected points change the evidence and
  the accessible data table contains the same values.
- Quarterly revenue delta is $5.2B (12.29%); capex delta is $3.3B (24.09%).
- Baseline/comparison chart controls select the appropriate evidence.
- Populated quarterly results fit the mobile viewport without page overflow
  (`scrollWidth == clientWidth == 375`). Viewport overrides were reset.
- Fixture browser console had no errors.

The browser automation download event did not complete, so actual JSON download
delivery is not verified. Token omission from chat exports passes regression
tests; that is a separate assertion from a successful browser download.

## Live AI findings and changes

The real Microsoft FY25 Q1 revenue query returned $13.2B, the **More Personal
Computing segment**, as company revenue and supplied no citation. Its recorded
pipeline time was 158.2 seconds, with 113.8 seconds in generation. This is an
accuracy failure, even though the number occurs in a retrieved passage.

The fix withholds answers lacking valid citations and checks figures against
the cited passages rather than every retrieved passage. Regression checks replay
the uncited/incorrect-source failure. The generation prompt now explicitly
distinguishes company totals from product/segment revenue. These checks do not
establish semantic correctness when a wrong figure is accompanied by a valid
segment citation. A fresh successful live RAG answer after the fix was not
verified; the stronger guard behavior is established by regression tests.

Real Meta Q1 2025 financial extraction exceeded the ten-minute proxy timeout.
The UI correctly displayed an error. The native quarterly AI run was not
completed because its metric-extraction prerequisite did not complete. Client
cancellation/timeouts do not interrupt an already running synchronous model;
the isolated API was stopped to terminate the test workload.

Other fixes discovered during verification:

- Fixed a TypeScript narrowing error in the financial response validator.
- Fixed the missing `Path` import used by the analytics cache default.
- Selected float32 for CPU generation; preserved automatic checkpoint precision on CUDA.
- Added explicit Undici header/body timeouts. Pinned a compatible major version
  after a real transport test exposed dispatcher protocol incompatibility.
- Added environment overrides to isolate the index, analytics cache and trace file.

## Reproduction and remaining work

Run the automated commands above before changing model configuration. Read-only
HTTP smoke checks can be repeated with:

```powershell
.venv/Scripts/python.exe tests/check_live_http.py --base http://127.0.0.1:13001
```

The controlled fixture API is in `tests/e2e_fixture_api.py`; it replaces model
output, never production code. With `.e2e` created, start it on loopback and point
a separate Next.js instance's `FINSIGHT_API_URL` at it:

```powershell
$env:FINSIGHT_FEEDBACK_DB = Join-Path (Get-Location) '.e2e/fixture-feedback.sqlite3'
.venv/Scripts/python.exe -m uvicorn tests.e2e_fixture_api:app --host 127.0.0.1 --port 18001
```

Next verification should use a configured stronger provider or adequate local
inference hardware, evaluate consolidated-versus-segment scope, complete native
metrics and quarterly comparisons, and verify JSON downloads in a browser with
download support. Production inference also needs bounded jobs and cooperative
or process-level cancellation so abandoned requests do not occupy the model lock.

Screenshots are retained in `.e2e/screenshots/`: citations/feedback, financial
trends, quarterly comparisons, mobile results and the actual extraction timeout.
