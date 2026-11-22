"""Vector index: FastEmbed (bge-small, runs on CPU) + Qdrant in local/embedded mode."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from tripwire.corpus.chunk import Chunk

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION = "reports"


def point_id(chunk_id: str) -> str:
    # Qdrant needs int or UUID ids; derive a stable UUID from our readable chunk id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def load_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f]


@dataclass
class Hit:
    chunk: Chunk
    score: float


class VectorIndex:
    def __init__(self, path: Path, collection: str = COLLECTION):
        self.client = QdrantClient(path=str(path))
        self.collection = collection
        self.embedder = TextEmbedding(EMBED_MODEL)

    def rebuild(self, chunks: Iterable[Chunk], batch: int = 256) -> int:
        chunks = list(chunks)
        dim = len(next(iter(self.embedder.embed(["probe"]))))
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            vectors = self.embedder.embed([c.text for c in part])
            self.client.upsert(self.collection, points=[
                models.PointStruct(id=point_id(c.id), vector=v.tolist(), payload=c.to_dict())
                for c, v in zip(part, vectors, strict=True)
            ])
        return len(chunks)

    def add(self, chunks: Iterable[Chunk]) -> None:
        """Insert extra chunks (used later to plant poisoned or 'internal' documents)."""
        chunks = list(chunks)
        vectors = self.embedder.embed([c.text for c in chunks])
        self.client.upsert(self.collection, points=[
            models.PointStruct(id=point_id(c.id), vector=v.tolist(), payload=c.to_dict())
            for c, v in zip(chunks, vectors, strict=True)
        ])

    def search(self, query: str, k: int = 5, doc_id: str | None = None) -> list[Hit]:
        qvec = next(iter(self.embedder.query_embed(query))).tolist()
        flt = None
        if doc_id:
            flt = models.Filter(must=[models.FieldCondition(
                key="doc_id", match=models.MatchValue(value=doc_id))])
        res = self.client.query_points(self.collection, query=qvec, limit=k, query_filter=flt)
        return [Hit(chunk=Chunk(**p.payload), score=p.score) for p in res.points]
