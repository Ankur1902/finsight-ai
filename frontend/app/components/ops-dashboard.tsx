"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../lib/api";
import type { OpsSummary } from "../../lib/types";

function parseOps(value: unknown): OpsSummary {
  const v = value as OpsSummary;
  if (
    !v ||
    typeof v !== "object" ||
    typeof v.stages !== "object" ||
    typeof v.routes !== "object"
  )
    throw new Error(
      "The research service returned an invalid operations summary.",
    );
  return v;
}
const usd = (x: number) => `$${x.toFixed(x < 0.01 ? 5 : 3)}`;

export default function OpsDashboard() {
  const [data, setData] = useState<OpsSummary | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      setData(await apiRequest("observability/summary", { decode: parseOps }));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed.");
    }
  }, []);
  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 10_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (error)
    return (
      <div role="alert" className="error">
        {error}
      </div>
    );
  if (!data) return <p className="muted">Loading…</p>;
  const stages = Object.entries(data.stages);
  const routes = Object.entries(data.routes);
  const lookups = data.semantic_cache.hits + data.semantic_cache.misses;
  return (
    <section className="ops-dashboard">
      <h2>Latency by pipeline stage</h2>
      {stages.length === 0 ? (
        <p className="muted">No requests yet. Ask a question in the chat.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Calls</th>
              <th>p50 (ms)</th>
              <th>p95 (ms)</th>
            </tr>
          </thead>
          <tbody>
            {stages.map(([name, s]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{s.count}</td>
                <td>{s.p50_ms}</td>
                <td>{s.p95_ms}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h2>Cost by model route (estimated)</h2>
      {routes.length === 0 ? (
        <p className="muted">No generations recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Route</th>
              <th>Requests</th>
              <th>Tokens in/out</th>
              <th>Total</th>
              <th>Per request</th>
              <th>Per correct answer</th>
            </tr>
          </thead>
          <tbody>
            {routes.map(([name, r]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{r.requests}</td>
                <td>
                  {r.tokens_in}/{r.tokens_out}
                </td>
                <td>{usd(r.cost_usd)}</td>
                <td>{usd(r.cost_per_request_usd)}</td>
                <td>
                  {r.cost_per_correct_answer_usd === null
                    ? "n/a (needs judged answers)"
                    : usd(r.cost_per_correct_answer_usd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted">
        Semantic cache: {data.semantic_cache.hits} hits / {lookups} lookups.
        Token counts are estimates (characters ÷ 4); prices are configurable in{" "}
        <code>src/observability.py</code>.
      </p>
    </section>
  );
}
