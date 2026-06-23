from langchain_core.prompts import PromptTemplate

RAG_PROMPT = PromptTemplate.from_template(
    """
You are a financial analyst assistant.

Answer ONLY using the provided context.

If the answer cannot be found in the context, say:
"I couldn't find that information in the provided documents."

Context:
{context}

Question:
{question}

Answer:
"""
)