"""Select a retrieval engine without importing/loading unused neural models."""
from .config import RETRIEVAL_MODE
from .runtime import generator_identity


def get_retriever():
    mode = RETRIEVAL_MODE
    if mode == "auto":
        mode = "lexical" if generator_identity().startswith("gemini:") else "hybrid"
    if mode == "hybrid":
        from .hybrid_retriever import get_hybrid_retriever
        return get_hybrid_retriever()
    if mode == "lexical":
        from .lexical_retriever import get_lexical_retriever
        return get_lexical_retriever()
    raise ValueError("FINSIGHT_RETRIEVAL_MODE must be auto, lexical or hybrid")
