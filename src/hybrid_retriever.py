"""Hybrid retrieval: metadata pre-filter -> BM25 + dense -> RRF -> cross-encoder.

Differences from a naive "retrieve 30 then filter" approach:
  * Filters are pushed *into* both searches (Chroma `where`, BM25 index mask),
    so a narrow question like "NVIDIA Q2 FY26 gross margin" searches only that
    transcript instead of hoping it survives a global top-30 cut.
  * Reciprocal Rank Fusion combines the two rankings instead of concatenating.
  * Comparison questions get one retrieval bucket per (company, period) so every
    side of the comparison is represented in the context.
"""

from __future__ import annotations

import re
from collections import defaultdict

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from .config import FETCH_K, RERANKER_MODEL, RETRIEVER_K, RRF_K
from .query_planner import QueryPlan, Target, plan_query
from .vectorstore import load_vectorstore


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _doc_key(doc: Document) -> str:
    return doc.metadata.get("chunk_id") or f"{doc.metadata.get('source')}|{doc.page_content[:120]}"


def _matches(meta: dict, target: Target) -> bool:
    if target.company and meta.get("company") != target.company:
        return False
    if target.quarter and meta.get("quarter") != target.quarter:
        return False
    if target.year and str(meta.get("year")) != target.year:
        return False
    return True


def _chroma_filter(target: Target) -> dict | None:
    clauses = [
        {key: value}
        for key, value in (("company", target.company), ("quarter", target.quarter), ("year", target.year))
        if value
    ]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _load_chunks_from_chroma(db) -> list[Document]:
    result = db._collection.get(include=["documents", "metadatas"])
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or [{}] * len(documents)
    return [Document(page_content=c, metadata=m or {}) for c, m in zip(documents, metadatas)]


class HybridRetriever:
    def __init__(self, vectorstore, chunks: list[Document], k: int = RETRIEVER_K, fetch_k: int = FETCH_K):
        self.k = k
        self.fetch_k = fetch_k
        self._vectorstore = vectorstore
        self._docs = chunks
        self._bm25 = BM25Okapi([_tokenize(d.page_content) for d in chunks])
        self._reranker: CrossEncoder | None = None
        self.catalog = self._build_catalog(chunks)

    @staticmethod
    def _build_catalog(chunks: list[Document]) -> dict[str, list[tuple[str, str]]]:
        """company -> [(quarter, year)] sorted by call date (oldest first)."""
        periods: dict[str, dict[tuple[str, str], str]] = defaultdict(dict)
        for doc in chunks:
            m = doc.metadata
            periods[m.get("company", "unknown")][(m.get("quarter"), str(m.get("year")))] = m.get("call_date", "")
        return {
            company: [p for p, _ in sorted(items.items(), key=lambda kv: kv[1])]
            for company, items in periods.items()
        }

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            self._reranker = CrossEncoder(RERANKER_MODEL)
        return self._reranker

    def _bm25_search(self, query: str, target: Target, k: int) -> list[Document]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            (
                (score, doc)
                for score, doc in zip(scores, self._docs)
                if score > 0 and _matches(doc.metadata, target)
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        return [doc for _, doc in ranked[:k]]

    def _vector_search(self, query: str, target: Target, k: int) -> list[Document]:
        return self._vectorstore.similarity_search(query, k=k, filter=_chroma_filter(target))

    @staticmethod
    def _rrf(*rankings: list[Document]) -> list[Document]:
        scores: dict[str, float] = defaultdict(float)
        by_key: dict[str, Document] = {}
        for ranking in rankings:
            for rank, doc in enumerate(ranking):
                key = _doc_key(doc)
                scores[key] += 1.0 / (RRF_K + rank + 1)
                by_key.setdefault(key, doc)
        return [by_key[key] for key in sorted(scores, key=scores.get, reverse=True)]

    def _rerank(self, query: str, docs: list[Document], k: int) -> list[Document]:
        if not docs:
            return []
        scores = self._get_reranker().predict([[query, d.page_content] for d in docs])
        ranked = sorted(zip(scores, docs), key=lambda item: item[0], reverse=True)[:k]
        out = []
        for score, doc in ranked:
            doc = Document(page_content=doc.page_content, metadata={**doc.metadata, "rerank_score": float(score)})
            out.append(doc)
        return out

    def retrieve_target(self, query: str, target: Target, k: int) -> list[Document]:
        fused = self._rrf(
            self._bm25_search(query, target, self.fetch_k),
            self._vector_search(query, target, self.fetch_k),
        )
        return self._rerank(query, fused[: self.fetch_k], k)

    def retrieve(self, query: str, plan: QueryPlan | None = None) -> list[Document]:
        plan = plan or plan_query(query, self.catalog)
        targets = plan.targets or [Target()]
        if len(targets) == 1:
            return self.retrieve_target(query, targets[0], self.k)

        # Comparison: guarantee coverage of every bucket, capped overall.
        per_target = max(2, min(self.k, 12 // len(targets)))
        docs: list[Document] = []
        for target in targets:
            docs.extend(self.retrieve_target(query, target, per_target))
        return docs

    # LangChain-style entry point, kept for the eval harness.
    def invoke(self, query: str) -> list[Document]:
        return self.retrieve(query)


_hybrid_retriever: HybridRetriever | None = None


def get_hybrid_retriever() -> HybridRetriever:
    global _hybrid_retriever
    if _hybrid_retriever is None:
        db = load_vectorstore()
        _hybrid_retriever = HybridRetriever(vectorstore=db, chunks=_load_chunks_from_chroma(db))
    return _hybrid_retriever
