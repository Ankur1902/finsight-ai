import hashlib

from langchain_core.documents import Document

from .config import CHUNK_OVERLAP, CHUNK_SIZE


def context_header(meta: dict) -> str:
    """Short provenance line prepended to every chunk.

    A chunk like "revenue was $65.6 billion, up 16%" is ambiguous on its own;
    embedding it together with company + fiscal period lets both BM25 and the
    dense retriever match questions such as "Microsoft FY25 Q1 revenue".
    """
    return (
        f"[{meta.get('company_name', meta.get('company', ''))} | "
        f"FY{meta.get('year', '?')} {meta.get('quarter', '?')} earnings call | "
        f"held {meta.get('call_date', 'unknown')} | page {meta.get('page', '?')}]"
    )


def chunk_id(meta: dict, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{meta.get('source', 'doc')}::p{meta.get('page', 0)}::{index}::{digest}"


def split_documents(documents: list[Document]) -> list[Document]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    )

    chunks: list[Document] = []
    for doc in documents:
        for index, piece in enumerate(splitter.split_text(doc.page_content)):
            meta = dict(doc.metadata)
            meta["chunk_id"] = chunk_id(meta, index, piece)
            chunks.append(
                Document(
                    page_content=f"{context_header(meta)}\n{piece}",
                    metadata=meta,
                )
            )
    return chunks
