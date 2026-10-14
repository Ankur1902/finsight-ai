import type { ChatAnswer, ChatMessage } from "./types";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function nullableText(value: unknown): boolean {
  return value === null || typeof value === "string";
}
function positiveId(value: unknown): boolean {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function parseChatAnswer(value: unknown): ChatAnswer {
  const invalid = () => {
    throw new Error(
      "The research service returned an invalid response. Please retry.",
    );
  };
  if (
    !object(value) ||
    typeof value.question !== "string" ||
    typeof value.answer !== "string" ||
    !value.answer.trim() ||
    typeof value.blocked !== "boolean" ||
    !Array.isArray(value.flags) ||
    !value.flags.every((flag) => typeof flag === "string") ||
    !Array.isArray(value.sources) ||
    !object(value.timings_ms) ||
    !Object.values(value.timings_ms).every(
      (ms) => typeof ms === "number" && Number.isFinite(ms) && ms >= 0,
    )
  )
    return invalid();
  const ids = new Set<number>();
  for (const source of value.sources) {
    if (
      !object(source) ||
      !positiveId(source.id) ||
      ids.has(source.id as number) ||
      typeof source.source !== "string" ||
      !source.source ||
      typeof source.excerpt !== "string" ||
      typeof source.snippet !== "string" ||
      !(source.page === null || positiveId(source.page)) ||
      !(
        source.score === null ||
        (typeof source.score === "number" && Number.isFinite(source.score))
      ) ||
      ![
        source.company,
        source.company_name,
        source.quarter,
        source.year,
        source.period,
        source.call_date,
      ].every(nullableText)
    )
      return invalid();
    ids.add(source.id as number);
  }
  if (value.plan !== null) {
    if (
      !object(value.plan) ||
      typeof value.plan.inherited !== "boolean" ||
      !Array.isArray(value.plan.targets) ||
      !value.plan.targets.every(
        (target) =>
          object(target) &&
          typeof target.label === "string" &&
          [target.company, target.quarter, target.year].every(nullableText),
      )
    )
      return invalid();
  }
  if (
    value.response_id !== undefined &&
    value.response_id !== null &&
    typeof value.response_id !== "string"
  )
    return invalid();
  if (
    value.feedback_token !== undefined &&
    value.feedback_token !== null &&
    typeof value.feedback_token !== "string"
  )
    return invalid();
  if (value.model !== undefined && !nullableText(value.model)) return invalid();
  if (value.cached !== undefined && typeof value.cached !== "boolean")
    return invalid();
  const responseId = value.response_id,
    token = value.feedback_token;
  if ((responseId == null) !== (token == null)) return invalid();
  if (
    responseId != null &&
    (typeof responseId !== "string" ||
      !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(
        responseId,
      ))
  )
    return invalid();
  if (
    token != null &&
    (typeof token !== "string" || token.length < 32 || token.length > 128)
  )
    return invalid();
  return value as ChatAnswer;
}

export function requestHistory(messages: ChatMessage[]) {
  return messages.slice(-12).map((message) => ({
    role: message.role,
    content: message.content.slice(0, 4000),
  }));
}

export function messageId(prefix: string): string {
  const suffix =
    globalThis.crypto?.randomUUID?.() ||
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

export function exportableMessages(messages: ChatMessage[]) {
  return messages.map((message) => {
    if (!message.response) return message;
    const { feedback_token: _token, ...response } = message.response;
    return { ...message, response };
  });
}
