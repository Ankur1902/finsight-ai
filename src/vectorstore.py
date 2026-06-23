from langchain_chroma import Chroma

from .embeddings import get_embeddings

PERSIST_DIR = "db"
RETRIEVER_K = 5


def build_vectorstore(chunks, batch_size: int = 32):
    embeddings = get_embeddings()

    db = Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
    )

    total = len(chunks)

    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        db.add_documents(batch)
        done = min(start + batch_size, total)
        print(f"Embedded chunks {done}/{total}", flush=True)

    print("All chunks added.", flush=True)
    return db


def load_vectorstore():
    embeddings = get_embeddings()

    return Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
    )


def get_retriever():
    from .hybrid_retriever import get_hybrid_retriever

    return get_hybrid_retriever()
