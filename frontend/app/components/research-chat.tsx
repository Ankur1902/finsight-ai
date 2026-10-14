"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatSource, Period } from "../../lib/types";
import CitationAnswer from "./citation-answer";
import AnswerFeedback from "./answer-feedback";
import AnswerAssessment from "./answer-assessment";
import { citedSourceIds } from "../../lib/citations";
import { apiRequest, downloadJson } from "../../lib/api";
import {
  messageId as newMessageId,
  parseChatAnswer,
  requestHistory,
  exportableMessages,
} from "../../lib/chat";

const WARNINGS: Record<string, string> = {
  model_refusal: "The model could not answer from the available evidence.",
  ungrounded_numbers:
    "Some figures could not be verified in the retrieved evidence.",
  uncited_answer: "This answer has no valid source citations.",
  invalid_citation: "Invalid source references were removed from the answer.",
  period_partially_covered:
    "Some requested fiscal periods are not covered by the index.",
  investment_advice_request:
    "This response provides reported facts, not investment advice.",
  advice_language:
    "The answer contains advice-like language. Treat it as research, not a recommendation.",
  pii_redacted: "Personal information was redacted from the request.",
  poisoned_chunks_removed:
    "Suspicious passages were excluded from the retrieved evidence.",
};

function warningLabels(flags: string[]) {
  return Array.from(
    new Set(flags.map((flag) => WARNINGS[flag.split(":")[0]]).filter(Boolean)),
  );
}

export default function ResearchChat({
  active,
  catalog,
  catalogLoading,
  catalogError,
  onRetryCatalog,
}: {
  active: boolean;
  catalog: Period[];
  catalogLoading: boolean;
  catalogError: string;
  onRetryCatalog: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [failedQuestion, setFailedQuestion] = useState("");
  const [selected, setSelected] = useState<{
    messageId: string;
    source: ChatSource;
  } | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [verifiedQuestions, setVerifiedQuestions] = useState<string[]>([]);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const pendingQuestion = useRef("");
  const bottom = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const busy = pending !== null;
  useEffect(() => {
    if (!active) return;
    const c = new AbortController();
    void apiRequest("questions", {
      signal: c.signal,
      decode: (value: unknown) => {
        if (
          !value ||
          typeof value !== "object" ||
          !("questions" in value) ||
          !Array.isArray(value.questions)
        )
          return [];
        return value.questions
          .filter(
            (row: unknown): row is { question: string } =>
              !!row &&
              typeof row === "object" &&
              "question" in row &&
              typeof row.question === "string" &&
              row.question.length > 0 &&
              row.question.length <= 1000,
          )
          .map((row) => row.question);
      },
    })
      .then((questions) => {
        if (!c.signal.aborted) setVerifiedQuestions(questions);
      })
      .catch(() => {
        if (!c.signal.aborted) setVerifiedQuestions([]);
      });
    return () => c.abort();
  }, [active, catalog]);

  const cancel = useCallback(() => {
    epoch.current++;
    controller.current?.abort();
    controller.current = null;
    setPending(null);
    if (pendingQuestion.current) setDraft(pendingQuestion.current);
    pendingQuestion.current = "";
  }, []);
  useEffect(() => {
    if (!active) cancel();
  }, [active, cancel]);
  useEffect(
    () => () => {
      epoch.current++;
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    if (active)
      bottom.current?.scrollIntoView({
        block: "nearest",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  }, [messages, pending, active]);

  async function send(text = draft) {
    const question = text.trim();
    if (!question || question.length > 1000 || controller.current) return;
    const c = new AbortController();
    controller.current = c;
    const id = ++epoch.current;
    pendingQuestion.current = question;
    setPending(question);
    setDraft("");
    setError("");
    setFailedQuestion("");
    try {
      const history = requestHistory(messages);
      const result = await apiRequest("chat", {
        signal: c.signal,
        body: { question, history },
        decode: parseChatAnswer,
      });
      if (id !== epoch.current || c.signal.aborted) return;
      const messageId = newMessageId("reply");
      setMessages((current) => [
        ...current,
        {
          id: newMessageId("question"),
          role: "user",
          content: result.question,
        },
        {
          id: messageId,
          role: "assistant",
          content: result.answer,
          response: result,
        },
      ]);
      const cited = citedSourceIds(
        result.answer,
        result.sources.map((source) => source.id),
      );
      const firstSource =
        result.sources.find((source) => source.id === cited[0]) ||
        result.sources[0];
      setSelected(firstSource ? { messageId, source: firstSource } : null);
    } catch (e) {
      if (id === epoch.current && !c.signal.aborted) {
        setError(
          e instanceof Error
            ? e.message
            : "Unable to reach the research service.",
        );
        setFailedQuestion(question);
        setDraft(question);
      }
    } finally {
      if (id === epoch.current) {
        setPending(null);
        pendingQuestion.current = "";
        controller.current = null;
      }
    }
  }

  function selectSource(messageId: string, source: ChatSource) {
    setSelected({ messageId, source });
    requestAnimationFrame(() => {
      panel.current?.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 900px)").matches)
        panel.current?.scrollIntoView({
          block: "start",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
        });
    });
  }
  function clear() {
    cancel();
    setMessages([]);
    setDraft("");
    setSelected(null);
    setError("");
    setFailedQuestion("");
    setCopyStatus("");
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus("Answer copied with its citation markers.");
    } catch {
      setCopyStatus(
        "Copy is unavailable. You can select and copy the answer text.",
      );
    }
  }
  function exportChat() {
    downloadJson(exportableMessages(messages), "finsight-research-chat.json");
  }
  const companies = Array.from(new Set(catalog.map((p) => p.company)));

  return (
    <section
      className="research-chat"
      hidden={!active}
      aria-label="Earnings research chat"
    >
      <div className="chat-toolbar">
        <span className="badge">GROUNDED IN EARNINGS CALLS</span>
        <div>
          <button
            type="button"
            className="secondary"
            disabled={!messages.length}
            onClick={exportChat}
          >
            Export chat ↓
          </button>
          <button type="button" className="secondary" onClick={clear}>
            New chat
          </button>
        </div>
      </div>
      <div className="chat-layout">
        <div className="chat-column">
          <div
            className="conversation"
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="Conversation"
          >
            {!messages.length && !busy && (
              <div className="chat-welcome">
                <div className="empty-icon">✧</div>
                <h2>Ask a question. Inspect the evidence.</h2>
                <p className="muted">
                  Research Meta, Microsoft, and NVIDIA earnings calls. Follow up
                  naturally and open the numbered citations to see the original
                  passages.
                </p>
                {verifiedQuestions.length > 0 && (
                  <div className="verified-questions">
                    <p className="muted">
                      Examples checked against transcript evidence. Future
                      answers can vary.
                    </p>
                    {verifiedQuestions.map((question) => (
                      <button
                        key={question}
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setDraft(question);
                          void send(question);
                        }}
                      >
                        {question} ↗
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {messages.map((message) => (
              <article
                className={`chat-message ${message.role}`}
                key={message.id}
              >
                <div className="message-heading">
                  <span className={`avatar ${message.role}`}>
                    {message.role === "user" ? "You" : "◈"}
                  </span>
                  <strong>
                    {message.role === "user" ? "You" : "Finsight"}
                  </strong>
                  {message.role === "assistant" && (
                    <button
                      type="button"
                      className="copy-answer"
                      onClick={() => void copy(message.content)}
                    >
                      Copy answer
                    </button>
                  )}
                </div>
                {message.role === "user" ? (
                  <p className="user-question">{message.content}</p>
                ) : (
                  message.response && (
                    <>
                      <CitationAnswer
                        answer={message.content}
                        sources={message.response.sources}
                        messageId={message.id}
                        onSelect={(source) => selectSource(message.id, source)}
                      />
                      <div className="answer-actions">
                        {message.response.cached && (
                          <span className="badge">CACHED ANSWER</span>
                        )}
                        <button
                          type="button"
                          className="secondary"
                          disabled={busy || message.response.blocked}
                          onClick={() => {
                            setDraft(
                              `Explain the answer to this question in plain language: ${message.response?.question.slice(0, 750)}. Explain financial terms and cite the transcript evidence again.`,
                            );
                            form.current?.querySelector("textarea")?.focus();
                          }}
                        >
                          Explain in plain language
                        </button>
                      </div>
                      <AnswerAssessment answer={message.response} />
                      {warningLabels(message.response.flags).map((label) => (
                        <p className="answer-warning" key={label}>
                          {label}
                        </p>
                      ))}
                      {message.response.blocked && (
                        <span className="badge">
                          REQUEST DECLINED OR INSUFFICIENT EVIDENCE
                        </span>
                      )}
                      {message.response.sources.length > 0 && (
                        <div
                          className="source-chips"
                          aria-label="Retrieved source passages"
                        >
                          {message.response.sources.map((source) => (
                            <button
                              type="button"
                              key={source.id}
                              onClick={() => selectSource(message.id, source)}
                              aria-pressed={
                                selected?.messageId === message.id &&
                                selected.source.id === source.id
                              }
                            >
                              [{source.id}]{" "}
                              {source.company_name ||
                                source.company ||
                                "Transcript"}{" "}
                              {source.quarter}{" "}
                              {source.year ? `FY${source.year}` : ""}
                              {source.page ? ` · p.${source.page}` : ""}
                            </button>
                          ))}
                        </div>
                      )}
                      <AnswerFeedback answer={message.response} />
                      <p className="message-meta">
                        {message.response.plan?.targets
                          .map((t) => t.label)
                          .join(" · ")}
                        {message.response.plan?.inherited
                          ? " · Scope inherited from the conversation"
                          : ""}
                        {message.response.timings_ms.total
                          ? ` · ${(message.response.timings_ms.total / 1000).toFixed(1)}s`
                          : ""}
                      </p>
                    </>
                  )
                )}
              </article>
            ))}
            {busy && (
              <>
                <article className="chat-message user">
                  <div className="message-heading">
                    <span className="avatar user">You</span>
                    <strong>You</strong>
                  </div>
                  <p className="user-question">{pending}</p>
                </article>
                <div className="chat-thinking" role="status">
                  <span className="spinner" /> Retrieving transcript evidence
                  and preparing an answer…
                </div>
              </>
            )}
            <div ref={bottom} />
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <button
                type="button"
                className="secondary"
                onClick={() => void send(failedQuestion)}
                disabled={busy}
              >
                Retry question
              </button>
            </div>
          )}
          <form
            className="chat-composer"
            ref={form}
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <label htmlFor="research-question" className="sr-only">
              Your earnings-call question
            </label>
            <textarea
              id="research-question"
              value={draft}
              readOnly={busy}
              placeholder="Ask about an earnings call, financial results, guidance, or risks…"
              rows={3}
              aria-describedby="composer-help"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  if (!busy) form.current?.requestSubmit();
                }
              }}
            />
            <div className="composer-bottom">
              <span
                id="composer-help"
                className={draft.length > 1000 ? "character-limit" : "muted"}
              >
                {draft.length}/1000 · Enter to send, Shift+Enter for a new line
              </span>
              {busy ? (
                <button type="button" className="secondary" onClick={cancel}>
                  Cancel request
                </button>
              ) : (
                <button
                  type="submit"
                  className="primary"
                  disabled={!draft.trim() || draft.trim().length > 1000}
                >
                  Ask Finsight ↑
                </button>
              )}
            </div>
          </form>
          <p className="chat-disclaimer">
            Answers use indexed transcript passages. Citations link to evidence,
            and do not guarantee that every interpretation is correct. Not
            investment advice.
          </p>
          {copyStatus && (
            <p className="muted" role="status">
              {copyStatus}
            </p>
          )}
        </div>
        <section
          className="evidence-panel"
          id="rag-evidence-panel"
          ref={panel}
          tabIndex={-1}
          aria-label="Source evidence"
        >
          {selected ? (
            <>
              <div className="evidence-heading">
                <span className="badge">SOURCE [{selected.source.id}]</span>
              </div>
              <h2>
                {selected.source.company_name ||
                  selected.source.company ||
                  "Transcript"}
              </h2>
              <p className="evidence-period">
                {selected.source.quarter}{" "}
                {selected.source.year ? `FY${selected.source.year}` : ""}
                {selected.source.page ? ` · Page ${selected.source.page}` : ""}
              </p>
              {selected.source.call_date &&
                selected.source.call_date !== "unknown" && (
                  <p className="muted">
                    Earnings call · {selected.source.call_date}
                  </p>
                )}
              <blockquote className="evidence-excerpt">
                {selected.source.excerpt || selected.source.snippet}
              </blockquote>
              <p className="evidence-filename">{selected.source.source}</p>
              {selected.source.source.toLowerCase().endsWith(".pdf") && (
                <a
                  className="pdf-link"
                  target="_blank"
                  rel="noreferrer"
                  href={`/api/documents/${encodeURIComponent(selected.source.source)}${selected.source.page ? `#page=${selected.source.page}` : ""}`}
                >
                  Open transcript
                  {selected.source.page
                    ? ` at page ${selected.source.page}`
                    : ""}{" "}
                  ↗
                </a>
              )}
              <p className="muted evidence-hint">
                Citation numbers belong to the selected answer. This is the full
                retrieved passage, not necessarily the entire PDF page.
              </p>
            </>
          ) : (
            <>
              <span className="badge">SOURCE EXPLORER</span>
              <h2>Your evidence, one click away</h2>
              <p className="muted">
                Click a numbered citation in an answer to inspect the original
                passage and open the PDF at its source page.
              </p>
              <div className="document-coverage">
                <h3>Available documents</h3>
                {catalogLoading && (
                  <p className="muted">Loading document coverage…</p>
                )}
                {catalogError && (
                  <>
                    <p className="muted">
                      Document coverage could not be loaded. You can still try
                      querying the existing index.
                    </p>
                    <button
                      type="button"
                      className="secondary"
                      onClick={onRetryCatalog}
                    >
                      Retry coverage
                    </button>
                  </>
                )}
                {!catalogLoading && !catalogError && !catalog.length && (
                  <p className="muted">
                    No PDF documents were found in the corpus.
                  </p>
                )}
                {companies.map((company) => (
                  <div key={company}>
                    <strong>
                      {catalog.find((p) => p.company === company)
                        ?.company_name || company}
                    </strong>
                    <p className="muted">
                      {catalog
                        .filter((p) => p.company === company)
                        .map((p) => `${p.quarter} FY${p.year}`)
                        .join(" · ")}
                    </p>
                  </div>
                ))}
              </div>
              <p className="muted evidence-hint">
                Document coverage is read from PDFs. Chat searches the vector
                index; new documents must be indexed before they can be cited.
              </p>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
