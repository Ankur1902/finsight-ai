"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Analysis, Metrics, Period } from "../../lib/types";
import { apiRequest } from "../../lib/api";
import { parseAnalysis, parseCatalog, parseMetrics } from "../../lib/contracts";

type Task = "metrics" | "history" | "changes";
type Selection = { company: string; period: string; baseline: string };

export function useAnalyticsWorkspace() {
  const [catalog, setCatalog] = useState<Period[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [selection, setSelection] = useState<Selection>({
    company: "meta",
    period: "",
    baseline: "",
  });
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [history, setHistory] = useState<Metrics[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  const catalogRequest = useRef<AbortController | null>(null);
  const epoch = useRef(0);

  const reloadCatalog = useCallback(() => {
    catalogRequest.current?.abort();
    const controller = new AbortController();
    catalogRequest.current = controller;
    setCatalogLoading(true);
    setCatalogError("");
    void apiRequest("catalog", {
      signal: controller.signal,
      decode: parseCatalog,
    })
      .then((rows) => {
        if (controller.signal.aborted) return;
        setCatalog(rows);
        setSelection((current) => {
          const available = rows.filter(
            (row) => row.company === current.company,
          );
          const selected =
            available.find((row) => row.period === current.period) ||
            available.at(-1);
          const earlier = selected
            ? available.filter(
                (row) =>
                  row.period !== selected.period &&
                  available.indexOf(row) < available.indexOf(selected),
              )
            : [];
          return {
            company: current.company,
            period: selected?.period || "",
            baseline:
              earlier.find((row) => row.period === current.baseline)?.period ||
              earlier.at(-1)?.period ||
              "",
          };
        });
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setCatalogError(
            err instanceof Error
              ? err.message
              : "Document coverage is unavailable.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
  }, []);
  useEffect(() => {
    reloadCatalog();
    return () => {
      epoch.current++;
      request.current?.abort();
      catalogRequest.current?.abort();
    };
  }, [reloadCatalog]);

  const cancel = useCallback(() => {
    epoch.current++;
    request.current?.abort();
    request.current = null;
    setTask(null);
    setError("");
  }, []);
  function resetResults() {
    cancel();
    setMetrics(null);
    setHistory([]);
    setAnalysis(null);
    setNotice("");
  }
  const periods = catalog.filter((row) => row.company === selection.company);
  const selectedIndex = periods.findIndex(
    (row) => row.period === selection.period,
  );
  const earlier = periods.slice(0, Math.max(0, selectedIndex));
  function selectCompany(company: string) {
    resetResults();
    const available = catalog.filter((row) => row.company === company);
    setSelection({
      company,
      period: available.at(-1)?.period || "",
      baseline: available.at(-2)?.period || "",
    });
  }
  function selectPeriod(period: string) {
    const index = periods.findIndex((row) => row.period === period);
    if (index < 0) return;
    resetResults();
    const prior = periods.slice(0, index);
    setSelection((current) => ({
      ...current,
      period,
      baseline: prior.some((row) => row.period === current.baseline)
        ? current.baseline
        : prior.at(-1)?.period || "",
    }));
  }
  function selectBaseline(baseline: string) {
    if (!earlier.some((row) => row.period === baseline)) return;
    cancel();
    setAnalysis(null);
    setNotice("");
    setSelection((current) => ({ ...current, baseline }));
  }
  async function perform(operation: Task) {
    const scope = { ...selection };
    if (!scope.period || (operation === "changes" && !scope.baseline)) return;
    cancel();
    const controller = new AbortController();
    request.current = controller;
    const id = ++epoch.current;
    setTask(operation);
    setError("");
    setNotice("");
    const current = () => id === epoch.current && !controller.signal.aborted;
    try {
      const path = (period: string) =>
        `metrics?company=${encodeURIComponent(scope.company)}&period=${encodeURIComponent(period)}`;
      if (operation === "metrics") {
        const result = await apiRequest(path(scope.period), {
          signal: controller.signal,
          decode: parseMetrics,
        });
        if (result.company !== scope.company || result.period !== scope.period)
          throw new Error(
            "Returned metrics do not match the selected company and period.",
          );
        if (current()) setMetrics(result);
      } else if (operation === "changes") {
        const result = await apiRequest("changes", {
          signal: controller.signal,
          body: {
            company: scope.company,
            before: scope.baseline,
            after: scope.period,
          },
          decode: parseAnalysis,
        });
        if (
          result.company !== scope.company ||
          result.before_period !== scope.baseline ||
          result.after_period !== scope.period
        )
          throw new Error(
            "Returned analysis does not match the selected periods.",
          );
        if (current()) setAnalysis(result);
      } else {
        const selected = periods.slice(
          Math.max(0, selectedIndex - 5),
          selectedIndex + 1,
        );
        const completed: Metrics[] = [];
        setHistory([]);
        setProgress({ completed: 0, total: selected.length });
        for (const row of selected) {
          const result = await apiRequest(path(row.period), {
            signal: controller.signal,
            decode: parseMetrics,
          });
          if (!current()) return;
          if (result.company !== scope.company || result.period !== row.period)
            throw new Error(
              "A historical result does not match its requested fiscal period.",
            );
          completed.push(result);
          setHistory([...completed]);
          setProgress({ completed: completed.length, total: selected.length });
        }
      }
    } catch (err) {
      if (current()) {
        setError(
          err instanceof Error
            ? err.message
            : "Analysis could not be completed.",
        );
        if (operation === "history")
          setNotice(
            "Historical analysis is incomplete. Completed observations remain available with their evidence.",
          );
      }
    } finally {
      if (current()) {
        request.current = null;
        setTask(null);
      }
    }
  }
  function cancelVisibleRequest() {
    cancel();
    setNotice(
      "Request cancelled. Previously completed results remain available.",
    );
  }
  const visibleMetrics =
    metrics?.company === selection.company &&
    metrics.period === selection.period
      ? metrics
      : null;
  const visibleAnalysis =
    analysis?.company === selection.company &&
    analysis.before_period === selection.baseline &&
    analysis.after_period === selection.period
      ? analysis
      : null;
  const visibleHistory = visibleMetrics
    ? history.filter((row) => row.company === selection.company)
    : [];
  return {
    catalog,
    catalogLoading,
    catalogError,
    reloadCatalog,
    selection,
    periods,
    earlier,
    metrics: visibleMetrics,
    history: visibleHistory,
    analysis: visibleAnalysis,
    task,
    progress,
    error,
    notice,
    cancel,
    cancelVisibleRequest,
    selectCompany,
    selectPeriod,
    selectBaseline,
    perform,
  };
}
