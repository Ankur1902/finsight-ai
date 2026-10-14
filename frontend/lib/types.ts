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
