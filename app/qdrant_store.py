"""Qdrant vector store client, diversified search, document reconstruction, and snapshot export."""

from collections import defaultdict
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
        for field in ("academia", "curso", "disciplina", "tipo", "path", "source_sha256"):
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def recreate_collection(self) -> dict[str, str]:
        """Drop and recreate the collection cleanly to purge stale/duplicate vectors."""
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.ensure_collection()
        return {"collection": self.collection_name, "status": "recreated"}

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Embed and upsert document chunks idempotently into Qdrant."""
        if not chunks:
            return 0
        self.ensure_collection()
        texts = [c["text"].strip() for c in chunks]
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
        max_per_source: int = 2,
    ) -> list[dict[str, Any]]:
        """Semantic search with payload filters and optional source diversification."""
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
        fetch_limit = min(60, limit * 3) if max_per_source > 0 else limit
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=query_filter,
            limit=fetch_limit,
            with_payload=True,
        )
        results = []
        per_path_counts: dict[str, int] = defaultdict(int)
        for hit in response.points:
            payload = hit.payload or {}
            path = payload.get("path", "")
            if max_per_source > 0 and path and per_path_counts[path] >= max_per_source:
                continue
            per_path_counts[path] += 1
            results.append(
                {
                    "score": round(float(hit.score), 4),
                    "title": payload.get("title", ""),
                    "text": payload.get("text", ""),
                    "academia": payload.get("academia", ""),
                    "curso": payload.get("curso", ""),
                    "disciplina": payload.get("disciplina", ""),
                    "tipo": payload.get("tipo", ""),
                    "path": path,
                    "chunk_index": payload.get("chunk_index", 0),
                }
            )
            if len(results) >= limit:
                break
        return results

    def get_document(self, path: str) -> dict[str, Any] | None:
        """Reconstruct a full indexed document by its exact canonical path."""
        if not self.client.collection_exists(self.collection_name):
            return None
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="path", match=models.MatchValue(value=path))]
            ),
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return None
        ordered = sorted(points, key=lambda p: (p.payload or {}).get("chunk_index", 0))
        first = ordered[0].payload or {}
        sections = []
        for p in ordered:
            txt = (p.payload or {}).get("text", "")
            if txt.startswith("[") and "\n" in txt:
                txt = txt.split("\n", 1)[1]
            sections.append(txt.strip())
        return {
            "path": path,
            "title": first.get("title", ""),
            "academia": first.get("academia", ""),
            "curso": first.get("curso", ""),
            "disciplina": first.get("disciplina", ""),
            "tipo": first.get("tipo", ""),
            "chunks_count": len(ordered),
            "text": "\n\n".join(sections),
        }

    def list_curated_assets(self) -> list[dict[str, str]]:
        """List all indexed Playbooks and Tactical Banks without duplicate chunk rows."""
        if not self.client.collection_exists(self.collection_name):
            return []
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tipo",
                        match=models.MatchAny(any=["playbook", "tactical_bank"]),
                    )
                ]
            ),
            limit=512,
            with_payload=["path", "title", "disciplina", "tipo"],
            with_vectors=False,
        )
        by_path: dict[str, dict[str, str]] = {}
        for p in points:
            pl = p.payload or {}
            path = pl.get("path", "")
            if path and path not in by_path:
                by_path[path] = {
                    "path": path,
                    "title": pl.get("title", ""),
                    "disciplina": pl.get("disciplina", ""),
                    "tipo": pl.get("tipo", ""),
                }
        return sorted(by_path.values(), key=lambda x: x["path"])

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
