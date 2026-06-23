from __future__ import annotations

import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from .vectorstore import load_vectorstore, RETRIEVER_K

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MERGE_FETCH_K = 30
METADATA_BOOST = 2.0


def _infer_query_filters(query: str) -> dict[str, str | None]:
    q = query.lower()
    company = None
    if "microsoft" in q or "msft" in q:
        company = "microsoft"
    elif "meta" in q:
        company = "meta"
    elif "nvidia" in q or "nvda" in q:
        company = "nvda"

    quarter = None
    quarter_match = re.search(r"\bq([1-4])\b", q, re.IGNORECASE)
    if quarter_match:
        quarter = f"Q{quarter_match.group(1)}"

    year = None
    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        year = year_match.group(1)
    elif re.search(r"fy(\d{2})", q, re.IGNORECASE):
        fy = re.search(r"fy(\d{2})", q, re.IGNORECASE).group(1)
        year = f"20{fy}"

    return {"company": company, "quarter": quarter, "year": year}


def _metadata_score(doc: Document, filters: dict[str, str | None]) -> float:
    score = 0.0
    meta = doc.metadata

    if filters["company"] and meta.get("company", "").lower() == filters["company"]:
        score += 1.0
    if filters["quarter"] and meta.get("quarter", "").upper() == filters["quarter"]:
        score += 0.75
    if filters["year"] and str(meta.get("year", "")) == filters["year"]:
        score += 0.75

    return score


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _doc_key(doc: Document) -> str:
    source = doc.metadata.get("source", "")
    snippet = doc.page_content[:120]
    return f"{source}|{snippet}"


def _load_chunks_from_chroma(db) -> list[Document]:
    result = db._collection.get(include=["documents", "metadatas"])
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or [{}] * len(documents)

    return [
        Document(page_content=content, metadata=meta or {})
        for content, meta in zip(documents, metadatas)
    ]


def _merge_documents(*doc_lists: list[Document]) -> list[Document]:
    merged: list[Document] = []
    seen: set[str] = set()

    for docs in doc_lists:
        for doc in docs:
            key = _doc_key(doc)
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)

    return merged


class HybridRetriever:
    """BM25 + vector search, merged and cross-encoder reranked."""

    def __init__(
        self,
        vectorstore,
        chunks: list[Document],
        k: int = RETRIEVER_K,
        fetch_k: int = MERGE_FETCH_K,
    ):
        self.k = k
        self.fetch_k = fetch_k
        self._vectorstore = vectorstore
        self._bm25_docs = chunks
        corpus = [_tokenize(doc.page_content) for doc in chunks]
        self._bm25 = BM25Okapi(corpus)
        self._reranker: CrossEncoder | None = None

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            self._reranker = CrossEncoder(RERANKER_MODEL)
        return self._reranker

    def _bm25_search(self, query: str, k: int) -> list[Document]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            zip(scores, self._bm25_docs),
            key=lambda item: item[0],
            reverse=True,
        )
        return [doc for score, doc in ranked[:k] if score > 0]

    def _vector_search(self, query: str, k: int) -> list[Document]:
        return self._vectorstore.similarity_search(query, k=k)

    def _apply_metadata_filter(
        self,
        docs: list[Document],
        filters: dict[str, str | None],
    ) -> list[Document]:
        if not filters["company"]:
            return docs

        company_docs = [
            doc
            for doc in docs
            if doc.metadata.get("company", "").lower() == filters["company"]
        ]

        if filters["quarter"] and filters["year"]:
            period_docs = [
                doc
                for doc in company_docs
                if doc.metadata.get("quarter", "").upper() == filters["quarter"]
                and str(doc.metadata.get("year", "")) == filters["year"]
            ]
            if period_docs:
                return period_docs

        if len(company_docs) >= self.k:
            return company_docs

        company_keys = {_doc_key(doc) for doc in company_docs}
        fallback = [doc for doc in docs if _doc_key(doc) not in company_keys]
        return company_docs + fallback

    def _rerank(
        self,
        query: str,
        docs: list[Document],
        filters: dict[str, str | None],
    ) -> list[Document]:
        if not docs:
            return []

        reranker = self._get_reranker()
        pairs = [[query, doc.page_content] for doc in docs]
        scores = reranker.predict(pairs)

        boosted = [
            float(score) + METADATA_BOOST * _metadata_score(doc, filters)
            for score, doc in zip(scores, docs)
        ]

        ranked = sorted(
            zip(boosted, docs),
            key=lambda item: item[0],
            reverse=True,
        )
        return [doc for _, doc in ranked[: self.k]]

    def invoke(self, query: str) -> list[Document]:
        filters = _infer_query_filters(query)
        bm25_docs = self._bm25_search(query, self.fetch_k)
        vector_docs = self._vector_search(query, self.fetch_k)
        merged = _merge_documents(bm25_docs, vector_docs)
        filtered = self._apply_metadata_filter(merged, filters)
        return self._rerank(query, filtered, filters)


_hybrid_retriever: HybridRetriever | None = None


def get_hybrid_retriever() -> HybridRetriever:
    global _hybrid_retriever

    if _hybrid_retriever is None:
        db = load_vectorstore()
        chunks = _load_chunks_from_chroma(db)
        _hybrid_retriever = HybridRetriever(vectorstore=db, chunks=chunks)

    return _hybrid_retriever
