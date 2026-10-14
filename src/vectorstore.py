from langchain_chroma import Chroma

from .config import COLLECTION_NAME, PERSIST_DIR
from .embeddings import get_embeddings


def build_vectorstore(chunks, batch_size: int = 32):
    """(Re)build the index. The collection is dropped first and chunk ids are
    deterministic, so re-running ingestion never duplicates chunks."""
    embeddings = get_embeddings()

    db = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
    )
    db.delete_collection()
    db = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )

    total = len(chunks)
    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        db.add_documents(batch, ids=[c.metadata["chunk_id"] for c in batch])
        done = min(start + batch_size, total)
        print(f"Embedded chunks {done}/{total}", flush=True)

    print("All chunks added.", flush=True)
    return db


def load_vectorstore():
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
        embedding_function=get_embeddings(),
    )


def get_retriever():
    from .hybrid_retriever import get_hybrid_retriever

    return get_hybrid_retriever()
