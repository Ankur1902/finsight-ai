from .llm import get_llm
from .prompts import RAG_PROMPT
from .vectorstore import get_retriever

retriever = None
llm = None


def initialize():
    global retriever, llm

    if retriever is None:
        retriever = get_retriever()

    if llm is None:
        llm = get_llm()


def retrieve(question: str):
    initialize()
    return retriever.invoke(question)


def ask(question: str):
    initialize()

    docs = retriever.invoke(question)
    context = "\n\n".join(doc.page_content for doc in docs)

    prompt = RAG_PROMPT.format(
        context=context,
        question=question,
    )

    answer = llm.invoke(prompt)

    sources = [
        {
            "source": doc.metadata.get("source", "Unknown"),
            "company": doc.metadata.get("company", "unknown"),
            "period": doc.metadata.get("period", "unknown"),
        }
        for doc in docs
    ]

    return answer, sources
