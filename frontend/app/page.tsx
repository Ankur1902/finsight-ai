"use client";

import { useState } from "react";
import ResearchChat from "./components/research-chat";
import FinancialDashboard from "./components/financial-dashboard";
import QuarterlyAnalyst from "./components/quarterly-analyst";
import { useAnalyticsWorkspace } from "./hooks/use-analytics-workspace";
import { periodLabel } from "../lib/finance";

type View = "chat" | "metrics" | "changes";
const VIEWS: Record<View, { title: string; description: string; nav: string }> =
  {
    chat: {
      title: "Earnings Research Assistant",
      description:
        "Ask about earnings calls and inspect the evidence behind each answer.",
      nav: "✧ Earnings research chat",
    },
    metrics: {
      title: "Financial Metric Dashboard",
      description:
        "Reported results, traceable figures, and fiscal-quarter trends.",
      nav: "▥ Financial metrics",
    },
    changes: {
      title: "Quarterly Change Analyst",
      description:
        "Compare financial results and understand changes in management commentary.",
      nav: "⇄ Quarterly changes",
    },
  };
const COMPANIES = [
  { id: "meta", label: "Meta" },
  { id: "microsoft", label: "Microsoft" },
  { id: "nvda", label: "NVIDIA" },
];

export default function Home() {
  const [view, setView] = useState<View>("chat");
  const workspace = useAnalyticsWorkspace();
  const { selection, task } = workspace;
  function navigate(next: View) {
    workspace.cancel();
    setView(next);
  }
  const taskLabel =
    task === "history"
      ? `Loading fiscal periods ${workspace.progress.completed}/${workspace.progress.total}`
      : task === "changes"
        ? "Comparing transcript evidence and financial results…"
        : "Extracting reported figures and validating quotations…";

  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/">
          ◈ Finsight
        </a>
        <p className="eyebrow">EARNINGS INTELLIGENCE</p>
        <nav aria-label="Research views">
          {(Object.keys(VIEWS) as View[]).map((key) => (
            <button
              type="button"
              key={key}
              className={view === key ? "active" : ""}
              aria-pressed={view === key}
              onClick={() => navigate(key)}
            >
              {VIEWS[key].nav}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="dot" /> Evidence first
          <p>Research grounded in company earnings calls.</p>
          <small>
            Fiscal periods differ across companies. Open the original evidence
            to review the figures.
          </small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">YOUR RESEARCH WORKSPACE</p>
            <h1>{VIEWS[view].title}</h1>
            <p className="muted">{VIEWS[view].description}</p>
          </div>
          <span className="badge">TRANSCRIPT RESEARCH</span>
        </header>
        {view !== "chat" && (
          <>
            {workspace.catalogError && (
              <div role="alert" className="error">
                {workspace.catalogError}
                <button
                  type="button"
                  className="secondary"
                  onClick={workspace.reloadCatalog}
                >
                  Retry coverage
                </button>
              </div>
            )}
            {!workspace.catalogLoading &&
              !workspace.catalogError &&
              !workspace.catalog.length && (
                <div className="empty">
                  Add supported company transcripts to the backend data
                  directory to begin.
                </div>
              )}
            <section className="filters" aria-label="Analysis filters">
              <label>
                Company
                <select
                  value={selection.company}
                  disabled={workspace.catalogLoading}
                  onChange={(event) =>
                    workspace.selectCompany(event.target.value)
                  }
                >
                  {COMPANIES.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.label}
                    </option>
                  ))}
                </select>
              </label>
              {view === "changes" && (
                <label>
                  Baseline
                  <select
                    value={selection.baseline}
                    disabled={!workspace.earlier.length}
                    onChange={(event) =>
                      workspace.selectBaseline(event.target.value)
                    }
                  >
                    {workspace.earlier.map((row) => (
                      <option key={row.period} value={row.period}>
                        {periodLabel(row.period)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                {view === "changes" ? "Compare with" : "Reporting period"}
                <select
                  value={selection.period}
                  disabled={!workspace.periods.length}
                  onChange={(event) =>
                    workspace.selectPeriod(event.target.value)
                  }
                >
                  {workspace.periods.map((row) => (
                    <option key={row.period} value={row.period}>
                      {periodLabel(row.period)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="primary"
                disabled={
                  task !== null ||
                  !selection.period ||
                  (view === "changes" && !selection.baseline)
                }
                onClick={() =>
                  void workspace.perform(
                    view === "metrics" ? "metrics" : "changes",
                  )
                }
              >
                {task
                  ? "Analyzing…"
                  : view === "metrics"
                    ? "Extract metrics →"
                    : "Analyze changes →"}
              </button>
            </section>
            {workspace.error && (
              <div role="alert" className="error">
                {workspace.error}
              </div>
            )}
            {workspace.notice && (
              <p className="notice" role="status">
                {workspace.notice}
              </p>
            )}
            {task && (
              <div className="loading" role="status">
                <span className="spinner" />
                <span>{taskLabel}</span>
                <button
                  type="button"
                  className="secondary"
                  onClick={workspace.cancelVisibleRequest}
                >
                  Cancel request
                </button>
              </div>
            )}
          </>
        )}
        <ResearchChat
          active={view === "chat"}
          catalog={workspace.catalog}
          catalogLoading={workspace.catalogLoading}
          catalogError={workspace.catalogError}
          onRetryCatalog={workspace.reloadCatalog}
        />
        {view === "metrics" && (
          <FinancialDashboard
            metrics={workspace.metrics}
            history={workspace.history}
            loadingHistory={task !== null}
            onLoadHistory={() => void workspace.perform("history")}
          />
        )}
        {view === "changes" && (
          <QuarterlyAnalyst
            analysis={workspace.analysis}
            enoughPeriods={workspace.periods.length >= 2}
          />
        )}
        <footer>
          Finsight · Earnings call research · Not investment advice
        </footer>
      </main>
    </div>
  );
}
