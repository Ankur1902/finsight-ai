import type { Fact, MetricChange, Metrics } from "./types";

export const METRIC_LABELS: Readonly<Record<string, string>> = {
  revenue: "Revenue",
  gross_margin: "Gross margin",
  operating_margin: "Operating margin",
  eps: "Diluted EPS",
  capex: "Capital expenditure",
  data_center_revenue: "Data Center revenue",
};
export function periodOrdinal(period: string): number {
  const match = /^Q([1-4])-(20\d{2})$/.exec(period);
  if (!match) throw new Error("Invalid fiscal period.");
  return Number(match[2]) * 4 + Number(match[1]) - 1;
}
export function periodLabel(period: string): string {
  const [quarter, year] = period.split("-");
  return `${quarter} FY${year}`;
}
export function formatFact(fact: Pick<Fact, "value" | "unit">): string {
  const magnitude = Math.abs(fact.value);
  const number =
    magnitude !== 0 && magnitude < 1e-12
      ? magnitude.toExponential()
      : new Intl.NumberFormat("en-US", { maximumFractionDigits: 12 }).format(
          magnitude,
        );
  const sign = fact.value < 0 ? "−" : "";
  const currency = fact.unit.startsWith("USD") ? "$" : "";
  const suffix =
    fact.unit === "percent"
      ? "%"
      : fact.unit === "USD billion"
        ? "B"
        : fact.unit === "USD million"
          ? "M"
          : fact.unit === "USD/share"
            ? " / share"
            : "";
  return `${sign}${currency}${number}${suffix}`;
}
export function seriesKey(fact: Fact): string {
  return JSON.stringify([fact.metric, fact.unit, fact.basis, fact.scope]);
}
export type TrendPoint = { period: string; fact: Fact };
export type FinancialSeries = {
  key: string;
  label: string;
  points: TrendPoint[];
};
export function financialSeries(
  results: Metrics[],
  metric: string,
): FinancialSeries[] {
  const groups = new Map<string, FinancialSeries>();
  const ambiguous = new Set<string>();
  for (const result of results)
    for (const fact of result.facts) {
      if (fact.metric !== metric || !Number.isFinite(fact.value)) continue;
      const key = seriesKey(fact);
      const observation = `${key}:${result.period}`;
      if (ambiguous.has(observation)) continue;
      const group = groups.get(key) || {
        key,
        label: `${fact.unit} · ${fact.basis} · ${fact.scope}`,
        points: [],
      };
      // Ambiguous duplicate observations are excluded rather than drawn twice.
      const duplicate = group.points.find((p) => p.period === result.period);
      if (duplicate && duplicate.fact.value !== fact.value) {
        ambiguous.add(observation);
        group.points = group.points.filter((p) => p.period !== result.period);
        groups.set(key, group);
        continue;
      }
      if (!duplicate) group.points.push({ period: result.period, fact });
      groups.set(key, group);
    }
  return [...groups.values()]
    .map((group) => ({
      ...group,
      points: group.points.sort(
        (a, b) => periodOrdinal(a.period) - periodOrdinal(b.period),
      ),
    }))
    .filter((group) => group.points.length > 0);
}
export function comparableChange(change: MetricChange): boolean {
  return (
    change.metric === change.before.metric &&
    change.metric === change.after.metric &&
    seriesKey(change.before) === seriesKey(change.after) &&
    Number.isFinite(change.before.value) &&
    Number.isFinite(change.after.value) &&
    Number.isFinite(change.delta.absolute)
  );
}
export function chartDomain(values: number[], unit: string): [number, number] {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return [0, 1];
  const min = Math.min(0, ...finite),
    max = Math.max(0, ...finite);
  if (unit === "percent") return [min < 0 ? min * 1.1 : 0, 100];
  const padding = Math.max(max - min, 1) * 0.1;
  return [min < 0 ? min - padding : 0, max > 0 ? max + padding : 1];
}

export function formatAxisValue(value: number, unit: string): string {
  if (unit === "percent")
    return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value)}%`;
  if (unit === "USD/share")
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(value);
  const scale = unit === "USD billion" ? 1e9 : unit === "USD million" ? 1e6 : 1;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value * scale);
}

export function formatAbsoluteChange(change: MetricChange): string {
  const sign = change.delta.absolute > 0 ? "+" : "";
  if (change.after.unit === "percent")
    return `${sign}${new Intl.NumberFormat("en-US", { maximumFractionDigits: 12 }).format(change.delta.absolute)} pp`;
  return `${sign}${formatFact({ value: change.delta.absolute, unit: change.after.unit })}`;
}
