"use client";

import { useEffect, useId, useRef, useState } from "react";
import type {
  ChatAnswer,
  FeedbackCategory,
  FeedbackRating,
} from "../../lib/types";
import { apiRequest } from "../../lib/api";
import { messageId } from "../../lib/chat";
import { parseFeedbackReceipt } from "../../lib/contracts";

const AREAS: { value: FeedbackCategory; label: string }[] = [
  { value: "accuracy", label: "Financial accuracy" },
  { value: "relevance", label: "Relevance" },
  { value: "clarity", label: "Clarity" },
  { value: "citations", label: "Citations" },
  { value: "missing_context", label: "Missing context" },
  { value: "fiscal_period", label: "Fiscal period" },
  { value: "units", label: "Units or calculations" },
];

export default function AnswerFeedback({ answer }: { answer: ChatAnswer }) {
  const id = useId();
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [categories, setCategories] = useState<FeedbackCategory[]>([]);
  const [sourceIds, setSourceIds] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [redacted, setRedacted] = useState(false);
  const submission = useRef("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function changed() {
    submission.current = "";
    setStatus("idle");
    setError("");
  }
  function choose(value: FeedbackRating) {
    changed();
    setRating(value);
    setEditing(true);
  }
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !rating ||
      !answer.response_id ||
      !answer.feedback_token ||
      controller.current
    )
      return;
    if (rating === "needs_improvement" && !categories.length) {
      setError("Choose at least one area that needs improvement.");
      return;
    }
    submission.current ||= messageId("feedback");
    const request = {
      response_id: answer.response_id,
      feedback_token: answer.feedback_token,
      submission_id: submission.current,
      rating,
      categories,
      note: note.trim(),
      source_ids: sourceIds,
    };
    const c = new AbortController();
    controller.current = c;
    setStatus("saving");
    setError("");
    try {
      const receipt = await apiRequest("feedback", {
        signal: c.signal,
        body: request,
        decode: parseFeedbackReceipt,
      });
      if (
        receipt.response_id !== answer.response_id ||
        receipt.submission_id !== submission.current
      )
        throw new Error(
          "The feedback receipt did not match this answer. Please retry.",
        );
      if (!c.signal.aborted) {
        setRedacted(receipt.note_redacted);
        setStatus("saved");
        setEditing(false);
      }
    } catch (err) {
      if (!c.signal.aborted) {
        setStatus("error");
        setError(
          err instanceof Error
            ? err.message
            : "Feedback could not be saved. Please retry.",
        );
      }
    } finally {
      if (controller.current === c) controller.current = null;
    }
  }
  if (!answer.response_id || !answer.feedback_token)
    return (
      <p className="feedback-unavailable">
        Feedback is unavailable for this reply. You can still inspect its
        citations.
      </p>
    );
  return (
    <section className="answer-feedback" aria-label="Answer feedback">
      <div className="feedback-heading">
        <span>Was this answer useful?</span>
        <div className="feedback-votes">
          <button
            type="button"
            aria-pressed={rating === "helpful"}
            disabled={status === "saving"}
            onClick={() => choose("helpful")}
          >
            ＋ Helpful
          </button>
          <button
            type="button"
            aria-pressed={rating === "needs_improvement"}
            disabled={status === "saving"}
            onClick={() => choose("needs_improvement")}
          >
            △ Needs improvement
          </button>
        </div>
      </div>
      {status === "saved" && !editing && (
        <p className="feedback-success" role="status">
          Feedback saved.
          {redacted
            ? " Personal information was redacted from your note."
            : ""}{" "}
          <button
            type="button"
            onClick={() => {
              changed();
              setEditing(true);
            }}
          >
            Edit feedback
          </button>
        </p>
      )}
      {editing && rating && (
        <form onSubmit={save}>
          <fieldset disabled={status === "saving"}>
            <legend>
              {rating === "helpful"
                ? "What worked well?"
                : "What needs attention?"}
            </legend>
            <div className="feedback-areas">
              {AREAS.map((area) => (
                <label key={area.value}>
                  <input
                    type="checkbox"
                    checked={categories.includes(area.value)}
                    onChange={(event) => {
                      changed();
                      setCategories((current) =>
                        event.target.checked
                          ? [...current, area.value]
                          : current.filter((value) => value !== area.value),
                      );
                    }}
                  />
                  {area.label}
                </label>
              ))}
            </div>
            {answer.sources.length > 0 && (
              <details>
                <summary>Attach source references (optional)</summary>
                <div className="feedback-areas">
                  {answer.sources.map((source) => (
                    <label key={source.id}>
                      <input
                        type="checkbox"
                        checked={sourceIds.includes(source.id)}
                        onChange={(event) => {
                          changed();
                          setSourceIds((current) =>
                            event.target.checked
                              ? [...current, source.id]
                              : current.filter((value) => value !== source.id),
                          );
                        }}
                      />
                      [{source.id}] {source.company_name || "Transcript"}
                      {source.page ? ` · p.${source.page}` : ""}
                    </label>
                  ))}
                </div>
              </details>
            )}
            <label className="feedback-note" htmlFor={`${id}-note`}>
              Add context (optional)
              <textarea
                id={`${id}-note`}
                rows={3}
                maxLength={1600}
                value={note}
                onChange={(event) => {
                  changed();
                  setNote(event.target.value);
                }}
                placeholder="For example: the answer used calendar Q1 instead of fiscal Q1, or the cited passage reports a different unit."
              />
            </label>
            <p className="muted feedback-privacy">
              Saved locally with this answer and its evidence. Avoid personal
              information. Feedback is used for review, not automatic model
              training.
            </p>
            <div className="feedback-actions">
              <span>{note.length}/1600</span>
              <button className="primary" type="submit">
                {status === "saving" ? "Saving…" : "Save feedback"}
              </button>
            </div>
          </fieldset>
          {error && (
            <p className="answer-warning" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
