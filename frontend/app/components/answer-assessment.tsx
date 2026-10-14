import type { ChatAnswer } from "../../lib/types";
import { citedSourceIds } from "../../lib/citations";

export default function AnswerAssessment({ answer }: { answer: ChatAnswer }) {
  const ids = citedSourceIds(
    answer.answer,
    answer.sources.map((source) => source.id),
  );
  return (
    <details className="answer-assessment">
      <summary>
        Understand this response <span>{ids.length} referenced sources</span>
      </summary>
      <dl>
        <div>
          <dt>Research scope</dt>
          <dd>
            {answer.plan?.targets.map((target) => target.label).join(" · ") ||
              "No reporting scope resolved"}
            {answer.plan?.inherited
              ? " · Inherited from your previous question"
              : ""}
          </dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>
            {ids.length
              ? `The answer references ${ids.map((id) => `[${id}]`).join(", ")} from ${answer.sources.length} retrieved passages.`
              : "No valid numbered source references were found."}{" "}
            Open citations to check the original wording, fiscal period, and
            units.
          </dd>
        </div>
        <div>
          <dt>Automated checks</dt>
          <dd>
            {answer.blocked
              ? "The request was declined or the pipeline abstained."
              : answer.flags.includes("ungrounded_numbers")
                ? "Some figures were not found in the retrieved excerpts. Review them before using the answer."
                : answer.flags.includes("uncited_answer")
                  ? "Source references are missing from this answer."
                  : "The pipeline returned the answer with its available evidence and notices."}
          </dd>
        </div>
        <div>
          <dt>Interpretation</dt>
          <dd>
            Source references show provenance. They do not establish that every
            claim is supported by the passage. Use the feedback form to report
            unclear explanations or incorrect comparisons.
          </dd>
        </div>
        {answer.model && (
          <div>
            <dt>Generator</dt>
            <dd>{answer.model}</dd>
          </div>
        )}
      </dl>
    </details>
  );
}
