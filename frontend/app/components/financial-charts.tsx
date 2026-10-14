"use client";

import { useId, useMemo, useState } from "react";
import type { Fact, MetricChange, Metrics } from "../../lib/types";
import {
  chartDomain,
  comparableChange,
  financialSeries,
  formatFact,
  formatAxisValue,
  formatAbsoluteChange,
  METRIC_LABELS,
  periodLabel,
  periodOrdinal,
} from "../../lib/finance";
import EvidenceExcerpt from "./evidence";

const WIDTH = 680,
  HEIGHT = 285,
  LEFT = 82,
  RIGHT = 24,
  TOP = 24,
  BOTTOM = 62;
const PLOT_WIDTH = WIDTH - LEFT - RIGHT,
  PLOT_HEIGHT = HEIGHT - TOP - BOTTOM;

function Axis({ domain, unit }: { domain: [number, number]; unit: string }) {
  const [min, max] = domain;
  return (
    <>
      {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
        const value = min + (max - min) * fraction;
        const y = TOP + PLOT_HEIGHT * (1 - fraction);
        return (
          <g key={fraction}>
            <line
              x1={LEFT}
              x2={WIDTH - RIGHT}
              y1={y}
              y2={y}
              className="chart-gridline"
            />
            <text
              x={LEFT - 12}
              y={y + 4}
              textAnchor="end"
              className="chart-axis-label"
            >
              {formatAxisValue(value, unit)}
            </text>
          </g>
        );
      })}
    </>
  );
}
function handlePointKey(
  event: React.KeyboardEvent<SVGGElement>,
  select: () => void,
) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    select();
  }
}

export function MetricTrends({ results }: { results: Metrics[] }) {
  const id = useId();
  const [metric, setMetric] = useState("revenue");
  const [groupKey, setGroupKey] = useState("");
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const groups = useMemo(
    () => financialSeries(results, metric),
    [results, metric],
  );
  const group = groups.find((row) => row.key === groupKey) || groups[0];
  const periods = useMemo(
    () =>
      [...new Set(results.map((row) => row.period))].sort(
        (a, b) => periodOrdinal(a) - periodOrdinal(b),
      ),
    [results],
  );
  const selected =
    group?.points.find((point) => point.period === selectedPeriod) ||
    group?.points.at(-1);
  if (!results.length)
    return (
      <div className="chart-empty">
        Load historical periods to plot reported metrics with their evidence.
      </div>
    );
  if (!group)
    return (
      <section className="chart-card">
        <div className="chart-controls">
          <label>
            Metric
            <select
              value={metric}
              onChange={(event) => setMetric(event.target.value)}
            >
              {Object.entries(METRIC_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="muted">
          No unambiguous figures are available for this metric in the selected
          periods.
        </p>
      </section>
    );
  const unit = group.points[0].fact.unit;
  const domain = chartDomain(
    group.points.map((point) => point.fact.value),
    unit,
  );
  const first = periodOrdinal(periods[0]),
    last = periodOrdinal(periods.at(-1)!);
  const x = (period: string) =>
    LEFT +
    (last === first
      ? PLOT_WIDTH / 2
      : ((periodOrdinal(period) - first) / (last - first)) * PLOT_WIDTH);
  const y = (value: number) =>
    TOP + PLOT_HEIGHT * (1 - (value - domain[0]) / (domain[1] - domain[0]));
  return (
    <section className="chart-card" aria-label="Financial metric trend">
      <div className="chart-controls">
        <label>
          Metric
          <select
            value={metric}
            onChange={(event) => {
              setMetric(event.target.value);
              setGroupKey("");
              setSelectedPeriod("");
            }}
          >
            {Object.entries(METRIC_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reporting basis
          <select
            value={group.key}
            onChange={(event) => {
              setGroupKey(event.target.value);
              setSelectedPeriod("");
            }}
          >
            {groups.map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="chart-heading">
        <div>
          <h3>{METRIC_LABELS[metric]} across fiscal periods</h3>
          <p className="muted">{group.label}</p>
        </div>
        {selected && (
          <div className="chart-selected-value">
            <strong>{formatFact(selected.fact)}</strong>
            <span>{periodLabel(selected.period)}</span>
          </div>
        )}
      </div>
      <svg
        className="financial-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-labelledby={`${id}-title ${id}-description`}
      >
        <title id={`${id}-title`}>{METRIC_LABELS[metric]} trend</title>
        <desc id={`${id}-description`}>
          Reported figures in {unit}, grouped by a matching accounting basis and
          scope. Missing quarters are not joined. Select a point or use the data
          table below to inspect evidence.
        </desc>
        <Axis domain={domain} unit={unit} />
        <line
          x1={LEFT}
          x2={WIDTH - RIGHT}
          y1={y(0)}
          y2={y(0)}
          className="chart-zero"
        />
        {group.points.slice(1).map((point, index) => {
          const previous = group.points[index];
          if (
            periodOrdinal(point.period) - periodOrdinal(previous.period) !==
            1
          )
            return null;
          return (
            <line
              key={point.period}
              x1={x(previous.period)}
              x2={x(point.period)}
              y1={y(previous.fact.value)}
              y2={y(point.fact.value)}
              className="chart-trend-line"
            />
          );
        })}
        {periods.map((period) => (
          <text
            key={period}
            x={x(period)}
            y={HEIGHT - 24}
            textAnchor="middle"
            className="chart-axis-label"
          >
            {periodLabel(period)}
          </text>
        ))}
        {group.points.map((point) => (
          <g
            key={point.period}
            role="button"
            tabIndex={0}
            aria-label={`${periodLabel(point.period)}, ${formatFact(point.fact)}. Inspect transcript evidence.`}
            aria-pressed={selected?.period === point.period}
            onClick={() => setSelectedPeriod(point.period)}
            onKeyDown={(event) =>
              handlePointKey(event, () => setSelectedPeriod(point.period))
            }
            className="chart-point-control"
          >
            <circle
              cx={x(point.period)}
              cy={y(point.fact.value)}
              r={selected?.period === point.period ? 7 : 5}
              className={
                selected?.period === point.period
                  ? "chart-point selected"
                  : "chart-point"
              }
            />
          </g>
        ))}
      </svg>
      <p className="chart-method">
        The axis includes zero; axis labels are rounded for readability.
        Selected observations retain extracted precision. Lines cover
        consecutive fiscal quarters only.
      </p>
      {selected && (
        <div className="chart-evidence">
          <strong>
            {periodLabel(selected.period)} · {formatFact(selected.fact)}
          </strong>
          <EvidenceExcerpt evidence={selected.fact.evidence} />
        </div>
      )}
      <details className="chart-data">
        <summary>View chart data and sources</summary>
        <div className="table-wrap">
          <table>
            <caption>
              Reported {METRIC_LABELS[metric]} · {group.label}
            </caption>
            <thead>
              <tr>
                <th>Period</th>
                <th>Value</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((period) => {
                const point = group.points.find((row) => row.period === period);
                return (
                  <tr key={period}>
                    <td>{periodLabel(period)}</td>
                    <td>{point ? formatFact(point.fact) : "Not available"}</td>
                    <td>
                      {point ? (
                        <button
                          className="table-evidence-button"
                          onClick={() => setSelectedPeriod(period)}
                          type="button"
                        >
                          Inspect page {point.fact.evidence.page}
                        </button>
                      ) : (
                        "No unambiguous extracted figure"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export function QuarterlyComparisonChart({
  changes,
  beforePeriod,
  afterPeriod,
}: {
  changes: MetricChange[];
  beforePeriod: string;
  afterPeriod: string;
}) {
  const id = useId();
  const eligible = changes.filter(comparableChange);
  const [selectedKey, setSelectedKey] = useState("");
  const [selectedSide, setSelectedSide] = useState<"before" | "after">("after");
  const key = (change: MetricChange) =>
    JSON.stringify([
      change.metric,
      change.basis,
      change.before.unit,
      change.before.scope,
    ]);
  const change =
    eligible.find((row) => key(row) === selectedKey) || eligible[0];
  if (!change)
    return (
      <div className="chart-empty">
        No comparable metric pair is available. Review the narrative evidence
        below.
      </div>
    );
  const domain = chartDomain(
    [change.before.value, change.after.value],
    change.before.unit,
  );
  const y = (value: number) =>
    TOP + PLOT_HEIGHT * (1 - (value - domain[0]) / (domain[1] - domain[0]));
  const bars: {
    side: "before" | "after";
    fact: Fact;
    period: string;
    x: number;
  }[] = [
    {
      side: "before",
      fact: change.before,
      period: beforePeriod,
      x: LEFT + PLOT_WIDTH * 0.22,
    },
    {
      side: "after",
      fact: change.after,
      period: afterPeriod,
      x: LEFT + PLOT_WIDTH * 0.64,
    },
  ];
  const selectedFact = selectedSide === "before" ? change.before : change.after;
  const absolute = formatAbsoluteChange(change);
  return (
    <section
      className="chart-card"
      aria-label="Selected-period metric comparison"
    >
      <div className="chart-controls">
        <label>
          Compare metric
          <select
            value={key(change)}
            onChange={(event) => {
              setSelectedKey(event.target.value);
              setSelectedSide("after");
            }}
          >
            {eligible.map((row) => (
              <option key={key(row)} value={key(row)}>
                {METRIC_LABELS[row.metric]} · {row.basis} · {row.before.unit}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="chart-heading">
        <div>
          <h3>{METRIC_LABELS[change.metric]}</h3>
          <p className="muted">
            {change.basis} · {change.before.scope} · {change.before.unit}
          </p>
        </div>
        <div className="chart-selected-value">
          <strong>{absolute}</strong>
          <span>Change across selected periods</span>
        </div>
      </div>
      <svg
        className="financial-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-labelledby={`${id}-title ${id}-description`}
      >
        <title id={`${id}-title`}>
          {METRIC_LABELS[change.metric]} comparison
        </title>
        <desc id={`${id}-description`}>
          {periodLabel(beforePeriod)}: {formatFact(change.before)}.{" "}
          {periodLabel(afterPeriod)}: {formatFact(change.after)}. Absolute
          change: {absolute}. The axis includes zero, and each bar opens its
          source evidence.
        </desc>
        <Axis domain={domain} unit={change.before.unit} />
        <line
          x1={LEFT}
          x2={WIDTH - RIGHT}
          y1={y(0)}
          y2={y(0)}
          className="chart-zero"
        />
        {bars.map((bar) => (
          <g
            key={bar.side}
            role="button"
            tabIndex={0}
            aria-label={`${periodLabel(bar.period)}, ${formatFact(bar.fact)}. Inspect evidence.`}
            aria-pressed={selectedSide === bar.side}
            className="chart-point-control"
            onClick={() => setSelectedSide(bar.side)}
            onKeyDown={(event) =>
              handlePointKey(event, () => setSelectedSide(bar.side))
            }
          >
            <rect
              x={bar.x}
              y={Math.min(y(bar.fact.value), y(0))}
              width={80}
              height={Math.max(1, Math.abs(y(bar.fact.value) - y(0)))}
              rx={5}
              className={`comparison-bar ${bar.side}${selectedSide === bar.side ? " selected" : ""}`}
            />
            <text
              x={bar.x + 40}
              y={HEIGHT - 24}
              textAnchor="middle"
              className="chart-axis-label"
            >
              {periodLabel(bar.period)}
            </text>
          </g>
        ))}
      </svg>
      <div className="chart-legend">
        <span>
          <i className="legend-before" /> Baseline
        </span>
        <span>
          <i className="legend-after" /> Comparison
        </span>
      </div>
      <p className="chart-method">
        {change.after.unit === "percent"
          ? "Margin differences are percentage points."
          : change.delta.relative_percent === null
            ? "Relative change is unavailable for a non-positive baseline."
            : `${change.delta.relative_percent.toLocaleString("en-US", { maximumFractionDigits: 2 })}% change relative to the positive baseline.`}{" "}
        Colors identify periods, without classifying the change as good or bad.
      </p>
      <div className="comparison-evidence-switch">
        <button
          type="button"
          aria-pressed={selectedSide === "before"}
          onClick={() => setSelectedSide("before")}
        >
          {periodLabel(beforePeriod)} · {formatFact(change.before)}
        </button>
        <button
          type="button"
          aria-pressed={selectedSide === "after"}
          onClick={() => setSelectedSide("after")}
        >
          {periodLabel(afterPeriod)} · {formatFact(change.after)}
        </button>
      </div>
      <EvidenceExcerpt evidence={selectedFact.evidence} />
    </section>
  );
}
