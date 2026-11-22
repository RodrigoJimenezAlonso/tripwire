"""Retriever that mixes planted documents into the real index at query time.

The real Qdrant index is never modified, so the baseline stays clean and every attack runs in
isolation. Planted chunks are embedded with the same model and ranked by the same cosine score,
so they compete with real chunks exactly as an uploaded document would.
"""

from __future__ import annotations

import math
from typing import Protocol

from tripwire.corpus.chunk import Chunk
from tripwire.target.index import Hit


class EmbeddingIndex(Protocol):
    def embed_query(self, query: str) -> list[float]: ...
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def search_vector(self, qvec: list[float], k: int = 5,
                      doc_id: str | None = None) -> list[Hit]: ...


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class PlantedRetriever:
    def __init__(self, base: EmbeddingIndex, planted: list[Chunk]):
        self.base = base
        self.planted = planted
        self._vectors = base.embed_passages([c.text for c in planted]) if planted else []

    def search(self, query: str, k: int = 5, doc_id: str | None = None) -> list[Hit]:
        qvec = self.base.embed_query(query)
        hits = self.base.search_vector(qvec, k=k, doc_id=doc_id)
        for chunk, vec in zip(self.planted, self._vectors, strict=True):
            if doc_id is None or chunk.doc_id == doc_id:
                hits.append(Hit(chunk=chunk, score=_cosine(qvec, vec)))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]
