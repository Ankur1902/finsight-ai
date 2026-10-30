export type Evidence = { source: string; page: number; quote: string };
export type Period = {
  company: string;
  company_name: string;
  period: string;
  quarter: string;
  year: string;
  call_date: string;
};
export type Fact = {
  metric: string;
  value: number;
  unit: string;
  basis: string;
  scope: string;
  evidence: Evidence;
};
export type Metrics = {
  company: string;
  period: string;
  facts: Fact[];
  conflicts: Fact[][];
  missing_metrics: string[];
  rejected_facts: number;
  failed_extractions: number;
  model: string;
  notice: string;
};
export type MetricChange = {
  metric: string;
  basis: string;
  before: Fact;
  after: Fact;
  delta: { absolute: number; relative_percent: number | null; unit: string };
};
export type Analysis = {
  company: string;
  before_period: string;
  after_period: string;
  changes: {
    topic: string;
    category: string;
    summary: string;
    before: Evidence;
    after: Evidence;
  }[];
  metric_changes: MetricChange[];
  model: string;
  notice: string;
  failed_extractions: number;
};

export type ChatSource = {
  id: number;
  source: string;
  company: string | null;
  company_name: string | null;
  quarter: string | null;
  year: string | null;
  period: string | null;
  call_date: string | null;
  page: number | null;
  score: number | null;
  snippet: string;
  excerpt: string;
};
export type ChatAnswer = {
  cached?: boolean;
  model?: string | null;
  response_id?: string | null;
  feedback_token?: string | null;
  question: string;
  answer: string;
  sources: ChatSource[];
  flags: string[];
  blocked: boolean;
  plan: {
    targets: {
      company: string | null;
      quarter: string | null;
      year: string | null;
      label: string;
    }[];
    inherited: boolean;
  } | null;
  timings_ms: Record<string, number>;
  claims?: Claim[];
  claim_summary?: ClaimSummary | null;
  calculations?: Calculation[];
  route?: string | null;
};
export type Claim = {
  text: string;
  citations: number[];
  status: "supported" | "partial" | "unsupported" | "uncited";
  support: number;
  ungrounded_numbers: string[];
};
export type ClaimSummary = {
  total: number;
  supported: number;
  partial: number;
  unsupported: number;
  uncited: number;
  support_rate: number;
};
export type Calculation = {
  op: string;
  label: string;
  result: string;
  text: string;
  sources: number[];
};
export type GuidanceRow = {
  metric: string;
  low: string;
  high: string;
  unit: string;
  quote: string;
  page: number;
  source: string;
  period: string;
  horizon: string;
  verdict: "beat" | "in_line" | "miss" | "no_actual" | "not_comparable";
  surprise_vs_midpoint_pct?: string | null;
  actual: {
    value: string;
    unit: string;
    quote: string;
    page: number;
    source: string;
  } | null;
};
export type GuidanceReport = {
  company: string;
  guided_in: string;
  reported_in: string | null;
  guidance: GuidanceRow[];
  notice: string;
};
export type StageStat = { count: number; p50_ms: number; p95_ms: number };
export type RouteStat = {
  requests: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  cost_per_request_usd: number;
  cost_per_correct_answer_usd: number | null;
};
export type OpsSummary = {
  stages: Record<string, StageStat>;
  routes: Record<string, RouteStat>;
  counters: Record<string, number>;
  semantic_cache: { hits: number; misses: number };
};
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatAnswer;
};

export type FeedbackRating = "helpful" | "needs_improvement";
export type FeedbackCategory =
  | "accuracy"
  | "relevance"
  | "clarity"
  | "citations"
  | "missing_context"
  | "fiscal_period"
  | "units";
export type FeedbackReceipt = {
  status: "saved";
  response_id: string;
  submission_id: string;
  rating: FeedbackRating;
  note_redacted: boolean;
};
