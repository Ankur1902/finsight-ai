"use client";

import { useState } from "react";
import { apiRequest } from "../../lib/api";
import { periodLabel } from "../../lib/finance";
import type { GuidanceReport, GuidanceRow, Period } from "../../lib/types";

const COMPANIES = [
  { id: "meta", label: "Meta" },
  { id: "microsoft", label: "Microsoft" },
  { id: "nvda", label: "NVIDIA" },
];
const METRIC_NAMES: Record<string, string> = {
  revenue: "Revenue",
  capex: "Capital expenditure",
  gross_margin: "Gross margin",
  operating_margin: "Operating margin",
};
const VERDICTS: Record<GuidanceRow["verdict"], string> = {
  beat: "Beat guidance",
  in_line: "In line",
  miss: "Missed guidance",
  no_actual: "No comparable actual found",
  not_comparable: "Different horizon (not compared)",
};

function parseReport(value: unknown): GuidanceReport {
  const v = value as GuidanceReport;
  if (!v || typeof v !== "object" || !Array.isArray(v.guidance))
    throw new Error(
      "The research service returned an invalid guidance report.",
    );
  return v;
}
function range(row: GuidanceRow) {
  const unit = row.unit === "percent" ? "%" : "";
  const fmt = (x: string) =>
    row.unit === "USD million"
      ? `$${(Number(x) / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })}B`
      : `${Number(x)}${unit}`;
  return row.low === row.high
    ? fmt(row.low)
    : `${fmt(row.low)} – ${fmt(row.high)}`;
}

export default function GuidanceTracker({ catalog }: { catalog: Period[] }) {
  const [company, setCompany] = useState("meta");
  const options = catalog.filter((p) => p.company === company);
  const [period, setPeriod] = useState("");
  const [report, setReport] = useState<GuidanceReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const chosen = options.some((p) => p.period === period)
    ? period
    : (options[0]?.period ?? "");

  async function load() {
    setBusy(true);
    setError("");
    try {
      setReport(
        await apiRequest(`guidance?company=${company}&period=${chosen}`, {
          decode: parseReport,
        }),
      );
    } catch (e) {
      setReport(null);
      setError(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="guidance-tracker">
      <div className="controls">
        <label>
          Company
          <select
            value={company}
            onChange={(e) => {
              setCompany(e.target.value);
              setReport(null);
            }}
          >
            {COMPANIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Guidance given in
          <select
            value={chosen}
            onChange={(e) => {
              setPeriod(e.target.value);
              setReport(null);
            }}
          >
            {options.map((p) => (
              <option key={p.period} value={p.period}>
                {periodLabel(p.period)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary"
          disabled={busy || !chosen}
          onClick={() => void load()}
        >
          {busy ? "Comparing…" : "Compare with results →"}
        </button>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {report && (
        <>
          <p className="notice" role="status">
            {report.reported_in
              ? `Guidance from ${periodLabel(report.guided_in)} compared with ${periodLabel(report.reported_in)} results. `
              : "No later reported quarter is available to compare. "}
            {report.notice}
          </p>
          {report.guidance.length === 0 && (
            <p className="muted">No numeric guidance found.</p>
          )}
          {report.guidance.map((row, i) => (
            <article key={i} className={`guidance-card verdict-${row.verdict}`}>
              <header>
                <strong>{METRIC_NAMES[row.metric] ?? row.metric}</strong>
                <span className="verdict">{VERDICTS[row.verdict]}</span>
              </header>
              <p>
                Guided <b>{range(row)}</b>
                {row.actual && (
                  <>
                    {" "}
                    → reported{" "}
                    <b>
                      {row.unit === "USD million"
                        ? `$${(Number(row.actual.value) / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })}B`
                        : `${row.actual.value}%`}
                    </b>
                    {row.surprise_vs_midpoint_pct &&
                      ` (${Number(row.surprise_vs_midpoint_pct) > 0 ? "+" : ""}${row.surprise_vs_midpoint_pct}% vs midpoint)`}
                  </>
                )}
              </p>
              <blockquote>
                “{row.quote}” <small>p.{row.page}</small>
              </blockquote>
              {row.actual && (
                <blockquote>
                  “{row.actual.quote}” <small>p.{row.actual.page}</small>
                </blockquote>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
