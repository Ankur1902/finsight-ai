import type {
  Analysis,
  Evidence,
  Fact,
  FeedbackReceipt,
  MetricChange,
  Metrics,
  Period,
} from "./types";
import {
  comparableChange,
  METRIC_LABELS,
  periodOrdinal,
  seriesKey,
} from "./finance";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function text(value: unknown): value is string {
  return typeof value === "string";
}
function count(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
function period(value: unknown): value is string {
  return text(value) && /^Q[1-4]-20\d{2}$/.test(value);
}
function evidence(value: unknown): value is Evidence {
  return (
    object(value) &&
    text(value.source) &&
    count(value.page) &&
    value.page > 0 &&
    text(value.quote)
  );
}
function fact(value: unknown): value is Fact {
  if (
    !object(value) ||
    !text(value.metric) ||
    !(value.metric in METRIC_LABELS) ||
    !finite(value.value) ||
    Math.abs(value.value) > 1e15 ||
    !text(value.unit) ||
    !["GAAP", "non-GAAP", "unspecified"].includes(String(value.basis)) ||
    !text(value.scope) ||
    !evidence(value.evidence)
  )
    return false;
  const allowed = value.metric.endsWith("margin")
    ? ["percent"]
    : value.metric === "eps"
      ? ["USD/share"]
      : ["USD", "USD million", "USD billion"];
  return (
    allowed.includes(value.unit) &&
    (value.unit !== "percent" || Math.abs(value.value) <= 100) &&
    value.scope ===
      (value.metric === "data_center_revenue" ? "Data Center" : "consolidated")
  );
}
function reject(): never {
  throw new Error(
    "The research service returned incompatible financial data. Please retry after checking the backend version.",
  );
}

export function parseCatalog(value: unknown): Period[] {
  if (!object(value) || !Array.isArray(value.periods)) return reject();
  const seen = new Set<string>();
  for (const row of value.periods) {
    if (
      !object(row) ||
      ![
        row.company,
        row.company_name,
        row.quarter,
        row.year,
        row.call_date,
      ].every(text) ||
      !period(row.period) ||
      `${row.quarter}-${row.year}` !== row.period ||
      !["meta", "microsoft", "nvda"].includes(String(row.company))
    )
      return reject();
    const key = `${row.company}:${row.period}`;
    if (seen.has(key)) return reject();
    seen.add(key);
  }
  return (value.periods as Period[])
    .slice()
    .sort(
      (a, b) =>
        a.company.localeCompare(b.company) ||
        periodOrdinal(a.period) - periodOrdinal(b.period),
    );
}
export function parseMetrics(value: unknown): Metrics {
  if (
    !object(value) ||
    !text(value.company) ||
    !period(value.period) ||
    !Array.isArray(value.facts) ||
    !value.facts.every(fact) ||
    !Array.isArray(value.conflicts) ||
    !value.conflicts.every(
      (group) => Array.isArray(group) && group.length >= 2 && group.every(fact),
    ) ||
    !Array.isArray(value.missing_metrics) ||
    !value.missing_metrics.every((id) => text(id) && id in METRIC_LABELS) ||
    !count(value.rejected_facts) ||
    !count(value.failed_extractions) ||
    !text(value.model) ||
    !text(value.notice)
  )
    return reject();
  const facts = value.facts as Fact[];
  const providedMissing = new Set(value.missing_metrics);
  if (
    providedMissing.size !== value.missing_metrics.length ||
    Object.keys(METRIC_LABELS).some(
      (metric) =>
        providedMissing.has(metric) ===
        facts.some((row) => row.metric === metric),
    )
  )
    return reject();
  const keys = facts.map(seriesKey);
  if (new Set(keys).size !== keys.length) return reject();
  return value as unknown as Metrics;
}
function change(value: unknown): value is MetricChange {
  if (
    !object(value) ||
    !fact(value.before) ||
    !fact(value.after) ||
    !object(value.delta) ||
    !text(value.metric) ||
    !text(value.basis) ||
    !finite(value.delta.absolute) ||
    !text(value.delta.unit) ||
    !(
      value.delta.relative_percent === null ||
      finite(value.delta.relative_percent)
    )
  )
    return false;
  const candidate = value as unknown as MetricChange;
  if (
    !comparableChange(candidate) ||
    candidate.basis !== candidate.before.basis ||
    candidate.delta.unit !==
      (candidate.after.unit === "percent"
        ? "percentage points"
        : candidate.after.unit)
  )
    return false;
  const expected = candidate.after.value - candidate.before.value;
  const tolerance = Math.max(
    1e-8,
    Number.EPSILON *
      Math.max(
        Math.abs(candidate.before.value),
        Math.abs(candidate.after.value),
      ) *
      8,
  );
  if (Math.abs(candidate.delta.absolute - expected) > tolerance) return false;
  if (candidate.before.value <= 0)
    return candidate.delta.relative_percent === null;
  const relative = (expected / candidate.before.value) * 100;
  if (!Number.isFinite(relative))
    return candidate.delta.relative_percent === null;
  return (
    candidate.delta.relative_percent !== null &&
    Math.abs(candidate.delta.relative_percent - relative) <=
      Math.max(1e-8, Math.abs(relative) * 1e-10)
  );
}
export function parseAnalysis(value: unknown): Analysis {
  if (
    !object(value) ||
    !text(value.company) ||
    !period(value.before_period) ||
    !period(value.after_period) ||
    periodOrdinal(value.before_period) >= periodOrdinal(value.after_period) ||
    !Array.isArray(value.metric_changes) ||
    !value.metric_changes.every(change) ||
    !Array.isArray(value.changes) ||
    !value.changes.every(
      (row) =>
        object(row) &&
        text(row.topic) &&
        text(row.summary) &&
        ["guidance", "risk", "investment", "business"].includes(
          String(row.category),
        ) &&
        evidence(row.before) &&
        evidence(row.after),
    ) ||
    !count(value.failed_extractions) ||
    !text(value.model) ||
    !text(value.notice)
  )
    return reject();
  return value as unknown as Analysis;
}
export function parseFeedbackReceipt(value: unknown): FeedbackReceipt {
  if (
    !object(value) ||
    value.status !== "saved" ||
    !text(value.response_id) ||
    !text(value.submission_id) ||
    !["helpful", "needs_improvement"].includes(String(value.rating)) ||
    typeof value.note_redacted !== "boolean"
  )
    return reject();
  return value as unknown as FeedbackReceipt;
}
