const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const cache = new Map();

// Compile real TS/TSX modules in memory; transport tests use an isolated loopback server.
function load(relative) {
  const filename = path.resolve(__dirname, "..", relative);
  if (cache.has(filename)) return cache.get(filename).exports;
  const mod = new Module(filename);
  mod.filename = filename;
  mod.paths = Module._nodeModulePaths(path.dirname(filename));
  cache.set(filename, mod);
  mod.require = function (id) {
    if (id.startsWith(".")) {
      const base = path.resolve(path.dirname(filename), id);
      for (const suffix of ["", ".ts", ".tsx"]) {
        if (fs.existsSync(base + suffix) && /\.tsx?$/.test(base + suffix))
          return load(
            path.relative(path.resolve(__dirname, ".."), base + suffix),
          );
      }
    }
    return Module.prototype.require.call(this, id);
  };
  const js = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  mod._compile(js, filename);
  return mod.exports;
}
const { remarkCitations, citationAnchor } = load("lib/citations.ts");
const CitationAnswer = load("app/components/citation-answer.tsx").default;

test("client deadline produces a safe timeout error", async () => {
  const { apiRequest } = load("lib/api.ts");
  const previous = global.fetch;
  global.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Test deadline was not enforced")), 100);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  });
  try {
    await assert.rejects(apiRequest("chat", { timeoutMs: 5, decode: value => value }),
      error => error.status === 504 && /timed out/.test(error.message));
  } finally {
    global.fetch = previous;
  }
});

test("client cancellation retains the caller's reason", async () => {
  const { apiRequest } = load("lib/api.ts");
  const controller = new AbortController();
  const reason = new DOMException("Cancelled by user", "AbortError");
  controller.abort(reason);
  const previous = global.fetch;
  global.fetch = async () => { throw reason; };
  try {
    await assert.rejects(apiRequest("chat", { signal: controller.signal, decode: value => value }),
      error => error === reason);
  } finally {
    global.fetch = previous;
  }
});

test("network failures never expose transport exception content", async () => {
  const { apiRequest } = load("lib/api.ts");
  const previous = global.fetch;
  global.fetch = async () => { throw new TypeError("private transport detail"); };
  try {
    await assert.rejects(apiRequest("catalog", { decode: value => value }),
      error => error.status === 503 && !error.message.includes("private"));
  } finally {
    global.fetch = previous;
  }
});
test("API errors identify a wrong backend without echoing upstream objects", async () => {
  const { apiRequest } = load("lib/api.ts");
  const previous = global.fetch;
  global.fetch = async () =>
    Response.json(
      { detail: { error: { code: "not_found", message: "Not Found" } } },
      { status: 404 },
    );
  try {
    await assert.rejects(
      apiRequest("catalog", { decode: (value) => value }),
      (error) =>
        error.status === 404 && error.message.includes("FINSIGHT_API_URL"),
    );
    global.fetch = async () =>
      Response.json({ detail: "Choose an earlier baseline." }, { status: 422 });
    await assert.rejects(
      apiRequest("changes", { body: {}, decode: (value) => value }),
      (error) =>
        error.status === 422 && error.message === "Choose an earlier baseline.",
    );
  } finally {
    global.fetch = previous;
  }
});
test("proxy dispatcher works with native Node fetch", async () => {
  const http = require("node:http");
  const server = http.createServer((_request, response) => {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ periods: [] }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const previous = process.env.FINSIGHT_API_URL;
  process.env.FINSIGHT_API_URL = `http://127.0.0.1:${server.address().port}`;
  try {
    const { GET } = load("app/api/[...path]/route.ts");
    const response = await GET(
      {
        method: "GET",
        nextUrl: { search: "" },
        signal: new AbortController().signal,
      },
      { params: Promise.resolve({ path: ["catalog"] }) },
    );
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { periods: [] });
  } finally {
    if (previous === undefined) delete process.env.FINSIGHT_API_URL;
    else process.env.FINSIGHT_API_URL = previous;
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});
const sources = [1, 2].map((id) => ({
  id,
  source: "microsoft.pdf",
  company: "microsoft",
  company_name: "Microsoft",
  quarter: "Q1",
  year: "2025",
  page: id,
  snippet: "Revenue excerpt",
  excerpt: "Full revenue excerpt",
}));
function render(answer, messageId = "reply-a") {
  return renderToStaticMarkup(
    React.createElement(CitationAnswer, {
      answer,
      messageId,
      sources,
      onSelect() {},
    }),
  );
}

test("single and grouped citations become scoped source links", () => {
  const tree = {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [{ type: "text", value: "Revenue [1, 2]. Unknown [7]." }],
      },
    ],
  };
  remarkCitations({ sourceIds: [1, 2], prefix: "reply-a" })(tree);
  const links = tree.children[0].children.filter(
    (node) => node.type === "link",
  );
  assert.deepEqual(
    links.map((node) => node.url),
    ["#reply-a-source-1", "#reply-a-source-2"],
  );
  assert.ok(tree.children[0].children.some((node) => node.value === "[7]"));
  assert.notEqual(citationAnchor("reply-a", 1), citationAnchor("reply-b", 1));
});

test("code and existing links are not rewritten into citations", () => {
  const tree = {
    type: "root",
    children: [
      { type: "code", value: "[1]" },
      {
        type: "link",
        url: "https://example.test",
        children: [{ type: "text", value: "[1]" }],
      },
    ],
  };
  const original = JSON.stringify(tree);
  remarkCitations({ sourceIds: [1], prefix: "reply-a" })(tree);
  assert.equal(JSON.stringify(tree), original);
});

test("actual answer component renders accessible citation buttons and Markdown", () => {
  const html = render("**Revenue** was $65.6 billion [1, 2]. Unknown [7].");
  assert.match(html, /<strong>Revenue<\/strong>/);
  assert.equal((html.match(/class="inline-citation"/g) || []).length, 2);
  assert.match(html, /aria-label="View source 1: Microsoft Q1 FY2025, page 1"/);
  assert.match(html, /Unknown \[7\]/);
});

test("comparison tables keep functioning citations", () => {
  const html = render(
    "| Metric | Value |\n| --- | --- |\n| Revenue | $65.6B [1] |",
  );
  assert.match(html, /<table>/);
  assert.match(html, /class="inline-citation"/);
});

test("untrusted answer HTML, images and external links cannot load content", () => {
  const html = render(
    "<script>alert(1)</script>\n\n![tracking](https://example.test/pixel.png)\n\n[external](https://example.test)\n\n`[1]`",
  );
  assert.doesNotMatch(html, /<script|<img|href="https:/);
  assert.match(html, /<code>\[1\]<\/code>/);
  assert.doesNotMatch(html, /class="inline-citation"/);
});

test("chat contract rejects malformed sources and scopes; history is bounded", () => {
  const { parseChatAnswer, requestHistory } = load("lib/chat.ts");
  const source = {
    ...sources[0],
    period: "Q1-2025",
    call_date: "2024-10-30",
    score: 4.2,
  };
  const valid = {
    question: "Revenue?",
    answer: "Revenue was $65.6B [1].",
    sources: [source],
    flags: [],
    blocked: false,
    plan: null,
    timings_ms: { total: 20 },
  };
  assert.equal(parseChatAnswer(valid).sources[0].id, 1);
  assert.throws(
    () => parseChatAnswer({ ...valid, sources: [{ ...source, id: "1" }] }),
    /invalid response/,
  );
  assert.throws(
    () => parseChatAnswer({ ...valid, sources: [source, source] }),
    /invalid response/,
  );
  assert.throws(
    () => parseChatAnswer({ ...valid, plan: {} }),
    /invalid response/,
  );
  const history = requestHistory(
    Array.from({ length: 20 }, (_, i) => ({
      id: String(i),
      role: "user",
      content: "x".repeat(5000),
    })),
  );
  assert.equal(history.length, 12);
  assert.equal(history[0].content.length, 4000);
});

test("Next.js proxy forwards the actual chat payload and full source response", async () => {
  const { POST } = load("app/api/[...path]/route.ts");
  const originalFetch = global.fetch;
  const originalUrl = process.env.FINSIGHT_API_URL;
  process.env.FINSIGHT_API_URL = "http://finsight-backend:8000";
  const body = {
    question: "And their capex?",
    history: [{ role: "user", content: "Meta Q2 2025 revenue?" }],
  };
  let called = false;
  global.fetch = async (url, options) => {
    called = true;
    assert.equal(String(url), "http://finsight-backend:8000/chat");
    assert.equal(options.method, "POST");
    assert.equal(typeof options.dispatcher.dispatch, "function");
    assert.ok(options.signal instanceof AbortSignal);
    assert.deepEqual(
      JSON.parse(Buffer.from(options.body).toString("utf8")),
      body,
    );
    return Response.json({
      answer: "Reported capex [1].",
      sources: [{ id: 1, excerpt: "Complete passage" }],
    });
  };
  try {
    const response = await POST(
      {
        method: "POST",
        nextUrl: { search: "" },
        signal: new AbortController().signal,
        headers: new Headers({ "Content-Type": "application/json" }),
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(JSON.stringify(body)));
            controller.close();
          },
        }),
      },
      { params: Promise.resolve({ path: ["chat"] }) },
    );
    assert.equal(response.status, 200);
    assert.equal(
      (await response.json()).sources[0].excerpt,
      "Complete passage",
    );
    assert.ok(called);
  } finally {
    global.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.FINSIGHT_API_URL;
    else process.env.FINSIGHT_API_URL = originalUrl;
  }
});

test("proxy errors are sanitized and unknown nested chat routes are denied", async () => {
  const { POST } = load("app/api/[...path]/route.ts");
  const originalFetch = global.fetch;
  global.fetch = async () => {
    throw new Error("private connection details");
  };
  const request = {
    method: "POST",
    nextUrl: { search: "" },
    signal: new AbortController().signal,
    headers: new Headers({ "Content-Type": "application/json" }),
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("{}"));
        controller.close();
      },
    }),
  };
  try {
    const response = await POST(request, {
      params: Promise.resolve({ path: ["chat"] }),
    });
    assert.equal(response.status, 503);
    assert.doesNotMatch(await response.text(), /private connection details/);
    assert.equal(
      (
        await POST(request, {
          params: Promise.resolve({ path: ["chat", "private"] }),
        })
      ).status,
      404,
    );
  } finally {
    global.fetch = originalFetch;
  }
});

test("financial series preserve gaps, negative values, and accounting-basis separation", () => {
  const { financialSeries, chartDomain, comparableChange } =
    load("lib/finance.ts");
  const evidence = { source: "report.pdf", page: 1, quote: "Actual results." };
  const base = {
    metric: "eps",
    value: -1,
    unit: "USD/share",
    basis: "GAAP",
    scope: "consolidated",
    evidence,
  };
  const results = [
    { period: "Q1-2025", facts: [base] },
    {
      period: "Q3-2025",
      facts: [
        { ...base, value: 2 },
        { ...base, basis: "non-GAAP", value: 3 },
      ],
    },
  ];
  const groups = financialSeries(results, "eps");
  assert.equal(groups.length, 2);
  assert.deepEqual(
    groups[0].points.map((point) => point.period),
    ["Q1-2025", "Q3-2025"],
  );
  const domain = chartDomain([-1, 2], "USD/share");
  assert.ok(domain[0] < 0 && domain[1] > 2);
  assert.equal(
    comparableChange({
      metric: "eps",
      before: base,
      after: { ...base, basis: "non-GAAP" },
      delta: { absolute: 0 },
    }),
    false,
  );
});

test("ambiguous observations cannot reappear after a third duplicate", () => {
  const { financialSeries } = load("lib/finance.ts");
  const base = {
    metric: "revenue",
    value: 42,
    unit: "USD billion",
    basis: "unspecified",
    scope: "consolidated",
    evidence: { source: "report.pdf", page: 1, quote: "Actual revenue." },
  };
  assert.equal(
    financialSeries(
      [{ period: "Q1-2025", facts: [base, { ...base, value: 43 }, base] }],
      "revenue",
    ).length,
    0,
  );
});

test("financial contracts reject mixed bases and inconsistent calculated deltas", () => {
  const { parseAnalysis } = load("lib/contracts.ts");
  const fact = {
    metric: "revenue",
    value: 40,
    unit: "USD billion",
    basis: "GAAP",
    scope: "consolidated",
    evidence: {
      source: "report.pdf",
      page: 1,
      quote: "Revenue was $40 billion.",
    },
  };
  const change = {
    metric: "revenue",
    basis: "GAAP",
    before: fact,
    after: { ...fact, value: 44 },
    delta: { absolute: 4, relative_percent: 10, unit: "USD billion" },
  };
  const analysis = {
    company: "meta",
    before_period: "Q1-2025",
    after_period: "Q2-2025",
    metric_changes: [change],
    changes: [],
    model: "test",
    notice: "Test",
    failed_extractions: 0,
  };
  assert.equal(parseAnalysis(analysis).metric_changes.length, 1);
  assert.throws(
    () =>
      parseAnalysis({
        ...analysis,
        metric_changes: [
          { ...change, delta: { ...change.delta, absolute: 9 } },
        ],
      }),
    /incompatible financial data/,
  );
  assert.throws(
    () =>
      parseAnalysis({
        ...analysis,
        metric_changes: [
          { ...change, after: { ...change.after, basis: "non-GAAP" } },
        ],
      }),
    /incompatible financial data/,
  );
});

test("chat export strips the private feedback capability token", () => {
  const { exportableMessages } = load("lib/chat.ts");
  const messages = [
    {
      id: "reply",
      role: "assistant",
      content: "Answer [1].",
      response: {
        response_id: "review-id",
        feedback_token: "private-token",
        sources: [],
      },
    },
  ];
  assert.equal(
    exportableMessages(messages)[0].response.feedback_token,
    undefined,
  );
  assert.equal(messages[0].response.feedback_token, "private-token");
});

test("proxy rejects unsupported methods and oversized feedback before forwarding", async () => {
  const { POST, GET } = load("app/api/[...path]/route.ts");
  const request = {
    method: "POST",
    headers: new Headers({
      "Content-Type": "application/json",
      "Content-Length": "300000",
    }),
    nextUrl: { search: "" },
    signal: new AbortController().signal,
  };
  assert.equal(
    (await POST(request, { params: Promise.resolve({ path: ["feedback"] }) }))
      .status,
    413,
  );
  assert.equal(
    (
      await GET(
        { ...request, method: "GET" },
        { params: Promise.resolve({ path: ["feedback"] }) },
      )
    ).status,
    405,
  );
});
