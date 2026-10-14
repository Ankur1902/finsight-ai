"""Fast metadata-scoped BM25 search over exact PDF passages, with no neural loading.

Lexical scores are not cross-encoder logits. Separate coverage checks govern
abstention. Hybrid semantic search remains selectable for broader evaluations.
"""
import re
from collections import defaultdict
from threading import RLock

from langchain_core.documents import Document
from rank_bm25 import BM25L

from .chunking import chunk_id, context_header
from .config import RETRIEVER_K
from .corpus import get_corpus
from .query_planner import Target, plan_query

STOP = set("what was were is are the a an of in for how did do does and about their its have has had company total consolidated fiscal quarter year call transcript microsoft meta nvidia nvda please tell me report reported results".split())
STOP.update("s it on to much fast according other our we with by at from".split())


def tokens(text):
    text = re.sub(r"\bcapex\b", "capital expenditures", text.lower())
    text = re.sub(r"\beps\b", "earnings per share", text)
    text = re.sub(r"\b(?:grew|grow|growing)\b", "growth", text)
    return [t for t in re.findall(r"\w+", text)
            if t not in STOP and not re.fullmatch(r"q[1-4]|fy\d+|20\d{2}", t)]


def matches(meta, target):
    return all(not value or str(meta.get(key)) == str(value)
               for key, value in (("company", target.company), ("quarter", target.quarter), ("year", target.year)))


class LexicalRetriever:
    def __init__(self, snapshot, k=RETRIEVER_K):
        self.k = k
        self.fingerprint = snapshot.fingerprint
        self.docs = []
        periods = defaultdict(set)
        for page in snapshot.pages:
            meta = page.metadata
            periods[meta.get("company")].add((meta.get("quarter"), str(meta.get("year"))))
            words = list(re.finditer(r"\S+", page.page_content))
            for index, start in enumerate(range(0, len(words), 175)):
                end = min(start + 220, len(words))
                body = page.page_content[words[start].start():words[end - 1].end()]
                metadata = {**meta, "chunk_id": chunk_id(meta, index, body)}
                self.docs.append(Document(page_content=f"{context_header(meta)}\n{body}", metadata=metadata))
        self.catalog = {company: sorted(rows, key=lambda p: (p[1], p[0])) for company, rows in periods.items()}
        self.terms = [set(tokens(d.page_content.split("\n", 1)[-1])) for d in self.docs]
        self.index = BM25L([tokens(d.page_content.split("\n", 1)[-1]) for d in self.docs]) if self.docs else None

    def retrieve_target(self, query, target, k):
        terms = list(dict.fromkeys(tokens(query)))
        if not terms or self.index is None:
            return []
        scores = self.index.get_scores(terms)
        ranked = []
        company_revenue = "revenue" in terms and not re.search(r"segment|cloud|azure|data center|advertising|family of apps|reality labs|gaming|productivity", query, re.I)
        for score, doc, vocabulary in zip(scores, self.docs, self.terms):
            coverage = len(set(terms) & vocabulary) / len(terms)
            if score <= 0 or coverage < 0.5 or not matches(doc.metadata, target):
                continue
            boost = 1.0
            priority = 0
            if company_revenue:
                body = re.sub(r"\s+", " ", doc.page_content.split("\n", 1)[-1])
                for match in re.finditer(r"\brevenue\s+(?:was|of)\s+\$\d+(?:\.\d+)?\s+(?:billion|million)\b", body, re.I):
                    prefix = body[max(0, match.start() - 100):match.start()]
                    if not re.search(r"family of apps|reality labs|cloud|data center|segment|personal computing|productivity|gaming|advertising|\bad\b|m365|expect|outlook|guidance", prefix, re.I):
                        priority = 1
            if company_revenue and re.search(r"\b(?:total|consolidated)\s+(?:company\s+)?revenue\b", doc.page_content, re.I):
                boost = 1.6
            if re.search(r"microsoft cloud", query, re.I) and re.search(r"microsoft cloud revenue", doc.page_content, re.I):
                boost = 2.0
            ranked.append((priority, float(score) * boost, coverage, doc))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [Document(page_content=d.page_content, metadata={**d.metadata,
                "retrieval_method": "lexical", "lexical_score": score, "term_coverage": coverage})
                for _, score, coverage, d in ranked[:k]]

    def retrieve(self, query, plan=None):
        plan = plan or plan_query(query, self.catalog)
        targets = plan.targets or [Target()]
        per_target = self.k if len(targets) == 1 else max(2, min(self.k, 12 // len(targets)))
        return [d for target in targets for d in self.retrieve_target(query, target, per_target)]

    def invoke(self, query):
        return self.retrieve(query)


_current = None
_lock = RLock()


def get_lexical_retriever():
    global _current
    snapshot = get_corpus()
    with _lock:
        if _current is None or _current.fingerprint != snapshot.fingerprint:
            _current = LexicalRetriever(snapshot)
        return _current
