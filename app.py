import streamlit as st

from src.retrieval import get_retriever
from src.llm import get_llm
from src.rag import COMPANY_LABELS, answer_question
from src.questions import verified_questions
from src.errors import GenerationError
from src.runtime import inference_context

st.set_page_config(page_title="Finsight", page_icon="📈", layout="wide")

FLAG_LABELS = {
    "pii_redacted": "🔒 Personal data redacted",
    "investment_advice_request": "⚖️ Advice request: facts only",
    "ungrounded_numbers": "⚠️ Unverified figures",
    "uncited_answer": "⚠️ Answer has no citations",
    "invalid_citation": "🧹 Invalid citations removed",
    "low_relevance": "🔎 No strong evidence found",
    "period_not_covered": "📅 Period not in corpus",
    "period_partially_covered": "📅 Some periods not in corpus",
    "prompt_injection": "🛡️ Prompt injection blocked",
    "out_of_coverage_company": "🏢 Company not covered",
    "poisoned_chunks_removed": "🛡️ Suspicious passages dropped",
}

EXAMPLES = [row["question"] for row in verified_questions()["questions"]]


@st.cache_resource(show_spinner="Loading index and models…")
def load():
    retriever = get_retriever()
    return retriever, get_llm()


def render_flags(flags):
    labels = []
    for flag in flags:
        key = flag.split(":")[0]
        if key in FLAG_LABELS:
            labels.append(FLAG_LABELS[key])
    if labels:
        st.caption(" · ".join(dict.fromkeys(labels)))


def render_sources(sources):
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for s in sources:
            st.markdown(
                f"**[{s['id']}] {s['company_name']} {s['quarter']} FY{s['year']}** "
                f"· call {s['call_date']} · p.{s['page']} · relevance {s['score']:.2f}  \n"
                f"`{s['source']}`"
            )
            st.caption(s["snippet"][:300] + "…")


retriever, llm = load()

with st.sidebar:
    st.header("📈 Finsight")
    st.caption(f"Model: `{llm.name}`")
    st.subheader("Coverage")
    for company, periods in retriever.catalog.items():
        st.markdown(
            f"**{COMPANY_LABELS.get(company, company)}**: "
            + ", ".join(f"{q} FY{y[2:]}" for q, y in periods)
        )
    st.caption("Periods are fiscal. Microsoft's FY starts in July; NVIDIA's ends in January.")
    st.subheader("Try")
    for example in EXAMPLES:
        if st.button(example, use_container_width=True):
            st.session_state.pending = example
    if st.button("Clear chat", type="secondary"):
        st.session_state.messages, st.session_state.last_plan = [], None
        st.rerun()

st.title("Earnings Call Analyst")
st.caption("Answers are grounded in transcript excerpts, cited by source number. Not investment advice.")

st.session_state.setdefault("messages", [])
st.session_state.setdefault("last_plan", None)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_flags(message.get("flags", []))
            render_sources(message.get("sources", []))

question = st.chat_input("Ask about Meta, Microsoft or NVIDIA earnings calls…") or st.session_state.pop("pending", None)

if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing transcripts…"):
            try:
                with inference_context():
                    resp = answer_question(question, history=history[-12:], previous_plan=st.session_state.last_plan)
            except GenerationError as exc:
                st.error(str(exc))
                st.stop()
            except Exception:
                st.error("Research is unavailable. Check backend configuration and retry.")
                st.stop()
        st.markdown(resp.answer)
        render_flags(resp.flags)
        render_sources(resp.sources)
        if resp.plan and resp.plan.targets and not resp.blocked:
            st.caption(
                "Searched: " + ", ".join(t.label() for t in resp.plan.targets)
                + (" (from conversation)" if resp.plan.inherited else "")
                + f" · {resp.timings_ms.get('total', 0) / 1000:.1f}s"
            )

    if resp.plan:
        st.session_state.last_plan = resp.plan
    st.session_state.messages.append(
        {"role": "assistant", "content": resp.answer, "sources": resp.sources, "flags": resp.flags}
    )
