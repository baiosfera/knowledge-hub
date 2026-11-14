"""Qdrant vector store client, schema initialization, search, and snapshot export."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.embedder import LazyEmbedder, get_embedder


class QdrantStore:
    """Manages the baiosfera_knowledge collection in Qdrant."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        embedder: LazyEmbedder | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.collection_name = collection_name or settings.qdrant_collection
        self.vector_size = vector_size or settings.embedding_dim
        self.embedder = embedder or get_embedder()
        self.client = client or QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            https=False,
            timeout=30.0,
        )

    def ensure_collection(self) -> None:
        """Create collection and payload indexes idempotently."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        for field in ("academia", "curso", "disciplina", "tipo", "source_sha256"):
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Embed and upsert document chunks idempotently into Qdrant."""
        if not chunks:
            return 0
        self.ensure_collection()
        texts = [f"{c.get('title', '')}\n\n{c['text']}".strip() for c in chunks]
        vectors = self.embedder.embed_documents(texts)
        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            sha = chunk.get("source_sha256") or chunk.get("path") or chunk.get("title", "doc")
            chunk_idx = chunk.get("chunk_index", idx)
            point_id = str(uuid5(NAMESPACE_URL, f"{sha}:{chunk_idx}"))
            payload = {
                "title": chunk.get("title", ""),
                "text": chunk["text"],
                "academia": chunk.get("academia", ""),
                "curso": chunk.get("curso", ""),
                "disciplina": chunk.get("disciplina", ""),
                "tipo": chunk.get("tipo", "lesson"),
                "path": chunk.get("path", ""),
                "source_sha256": sha,
                "chunk_index": chunk_idx,
            }
            points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def search(
        self,
        query: str,
        limit: int = 8,
        academia: str | None = None,
        curso: str | None = None,
        disciplina: str | None = None,
        tipo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional metadata payload filters."""
        if not self.client.collection_exists(self.collection_name):
            return []
        must = []
        for key, val in (
            ("academia", academia),
            ("curso", curso),
            ("disciplina", disciplina),
            ("tipo", tipo),
        ):
            if val:
                must.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=val),
                    )
                )
        query_filter = models.Filter(must=must) if must else None
        vector = self.embedder.embed_query(query)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        results = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append(
                {
                    "score": round(float(hit.score), 4),
                    "title": payload.get("title", ""),
                    "text": payload.get("text", ""),
                    "academia": payload.get("academia", ""),
                    "curso": payload.get("curso", ""),
                    "disciplina": payload.get("disciplina", ""),
                    "tipo": payload.get("tipo", ""),
                    "path": payload.get("path", ""),
                }
            )
        return results

    def stats(self) -> dict[str, Any]:
        """Return collection point count and status."""
        if not self.client.collection_exists(self.collection_name):
            return {"collection": self.collection_name, "exists": False, "points_count": 0}
        info = self.client.get_collection(self.collection_name)
        return {
            "collection": self.collection_name,
            "exists": True,
            "status": str(info.status),
            "points_count": info.points_count or 0,
        }

    def create_snapshot(self) -> str:
        """Create a portable Qdrant snapshot and return its filename."""
        snap = self.client.create_snapshot(collection_name=self.collection_name)
        return snap.name


_store: QdrantStore | None = None


def get_store() -> QdrantStore:
    """Return process-wide QdrantStore instance."""
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store
