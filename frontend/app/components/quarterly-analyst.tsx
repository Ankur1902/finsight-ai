import type { Analysis } from "../../lib/types";
import { downloadJson } from "../../lib/api";
import {
  formatFact,
  formatAbsoluteChange,
  METRIC_LABELS,
  periodLabel,
  periodOrdinal,
} from "../../lib/finance";
import EvidenceExcerpt from "./evidence";
import { QuarterlyComparisonChart } from "./financial-charts";

export default function QuarterlyAnalyst({
  analysis,
  enoughPeriods,
}: {
  analysis: Analysis | null;
  enoughPeriods: boolean;
}) {
  if (!analysis)
    return (
      <section className="empty">
        <div className="empty-icon">⇄</div>
        <h2>Understand the story behind the quarter</h2>
        <p>
          Compare reporting periods with original quotations and calculated
          financial differences.
        </p>
        {!enoughPeriods && (
          <p className="notice">At least two reporting periods are needed.</p>
        )}
      </section>
    );
  const distance =
    periodOrdinal(analysis.after_period) -
    periodOrdinal(analysis.before_period);
  return (
    <section aria-label="Quarterly analysis results">
      <div className="section-heading">
        <h2>
          {periodLabel(analysis.before_period)} →{" "}
          {periodLabel(analysis.after_period)}
        </h2>
        <button
          className="secondary"
          type="button"
          onClick={() =>
            downloadJson(
              analysis,
              `${analysis.company}-quarterly-analysis.json`,
            )
          }
        >
          Export analysis JSON ↓
        </button>
      </div>
      <p className="notice">{analysis.notice}</p>
      {distance > 1 && (
        <p className="notice">
          This comparison spans {distance} fiscal quarters. Differences refer to
          the selected periods.
        </p>
      )}
      <div className="analysis-stats">
        <div>
          <span>Comparable metrics</span>
          <strong>{analysis.metric_changes.length}</strong>
        </div>
        <div>
          <span>AI narrative findings</span>
          <strong>{analysis.changes.length}</strong>
        </div>
        <div>
          <span>Extraction issues</span>
          <strong>{analysis.failed_extractions}</strong>
        </div>
      </div>
      <QuarterlyComparisonChart
        changes={analysis.metric_changes}
        beforePeriod={analysis.before_period}
        afterPeriod={analysis.after_period}
      />
      {analysis.failed_extractions > 0 && (
        <p className="notice">
          {analysis.failed_extractions} responses failed validation. Analysis
          may be incomplete.
        </p>
      )}
      {analysis.metric_changes.length > 0 && (
        <details className="chart-data">
          <summary>Review all metric changes and evidence</summary>
          <div className="table-wrap">
            <table>
              <caption>
                Changes calculated from comparable actual results
              </caption>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Comparison</th>
                  <th>Absolute change</th>
                </tr>
              </thead>
              <tbody>
                {analysis.metric_changes.map((change, index) => (
                  <tr key={index}>
                    <td>
                      {METRIC_LABELS[change.metric]}
                      <small>
                        {change.basis} · {change.before.scope}
                      </small>
                    </td>
                    <td>
                      {formatFact(change.before)}
                      <EvidenceExcerpt evidence={change.before.evidence} />
                    </td>
                    <td>
                      {formatFact(change.after)}
                      <EvidenceExcerpt evidence={change.after.evidence} />
                    </td>
                    <td>
                      {formatAbsoluteChange(change)}
                      <small>
                        {change.after.unit === "percent"
                          ? "Percentage-point difference"
                          : change.delta.relative_percent === null
                            ? "Relative change unavailable"
                            : `${change.delta.relative_percent.toFixed(2)}% relative change`}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <div className="section-heading">
        <h2>What management commentary reveals</h2>
        <span className="badge">AI INTERPRETATIONS</span>
      </div>
      <div className="changes-grid">
        {analysis.changes.map((change, index) => (
          <article className="change-card" key={`${change.topic}-${index}`}>
            <span className="badge">{change.category}</span>
            <h3>{change.topic}</h3>
            <p>{change.summary}</p>
            <div className="quotes">
              <div>
                <p className="eyebrow">
                  Before · {periodLabel(analysis.before_period)}
                </p>
                <EvidenceExcerpt evidence={change.before} />
              </div>
              <div>
                <p className="eyebrow">
                  After · {periodLabel(analysis.after_period)}
                </p>
                <EvidenceExcerpt evidence={change.after} />
              </div>
            </div>
          </article>
        ))}
      </div>
      {!analysis.changes.length && (
        <p className="empty">
          No narrative changes passed evidence validation. This result does not
          establish that management commentary was unchanged.
        </p>
      )}
      <p className="model-note">Generated by {analysis.model}</p>
    </section>
  );
}
