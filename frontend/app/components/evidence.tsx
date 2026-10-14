import type { Evidence } from "../../lib/types";

export default function EvidenceExcerpt({
  evidence,
  open = false,
}: {
  evidence: Evidence;
  open?: boolean;
}) {
  return (
    <details className="source" open={open || undefined}>
      <summary>Transcript evidence · page {evidence.page}</summary>
      <blockquote>{evidence.quote}</blockquote>
      <a
        href={`/api/documents/${encodeURIComponent(evidence.source)}#page=${evidence.page}`}
        target="_blank"
        rel="noreferrer"
      >
        {evidence.source} ↗
      </a>
    </details>
  );
}
