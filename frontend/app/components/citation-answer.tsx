import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { citationAnchor, remarkCitations } from "../../lib/citations";
import type { ChatSource } from "../../lib/types";

export default function CitationAnswer({
  answer,
  sources,
  messageId,
  onSelect,
}: {
  answer: string;
  sources: ChatSource[];
  messageId: string;
  onSelect: (source: ChatSource) => void;
}) {
  const byAnchor = new Map(
    sources.map((source) => [citationAnchor(messageId, source.id), source]),
  );
  return (
    <div className="answer-markdown">
      <Markdown
        skipHtml
        remarkPlugins={[
          remarkGfm,
          [
            remarkCitations,
            { sourceIds: sources.map((s) => s.id), prefix: messageId },
          ],
        ]}
        components={{
          a: ({ href, children }) => {
            const source = byAnchor.get(href || "");
            if (!source) return <span>{children}</span>;
            const period = [
              source.quarter,
              source.year ? `FY${source.year}` : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <button
                type="button"
                className="inline-citation"
                aria-controls="rag-evidence-panel"
                aria-label={`View source ${source.id}: ${source.company_name || source.company || "Transcript"} ${period}${source.page ? `, page ${source.page}` : ""}`}
                title={source.source}
                onClick={() => onSelect(source)}
              >
                {children}
              </button>
            );
          },
          img: ({ alt }) => <span>{alt || "Image omitted"}</span>,
          table: ({ children }) => (
            <div className="answer-table">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {answer}
      </Markdown>
    </div>
  );
}
