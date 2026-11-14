"""Lazy-loaded FastEmbed ONNX embedder to keep idle RAM under 512 MB."""

import os
from threading import Lock
from typing import Iterable

from app.config import get_settings


class LazyEmbedder:
    """Thread-safe lazy singleton for FastEmbed TextEmbedding."""

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.cache_dir = cache_dir or settings.fastembed_cache_path
        self._model = None
        self._lock = Lock()

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    os.makedirs(self.cache_dir, exist_ok=True)
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=self.cache_dir,
                        threads=1,
                    )
        return self._model

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed document passages (adds E5 'passage: ' prefix when using E5)."""
        items = list(texts)
        if not items:
            return []
        if "e5" in self.model_name.lower():
            items = [f"passage: {t}" for t in items]
        model = self._ensure_model()
        return [vec.tolist() for vec in model.embed(items)]

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query (adds E5 'query: ' prefix when using E5)."""
        text = f"query: {query}" if "e5" in self.model_name.lower() else query
        model = self._ensure_model()
        return next(iter(model.embed([text]))).tolist()


_embedder: LazyEmbedder | None = None


def get_embedder() -> LazyEmbedder:
    """Return process-wide lazy embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = LazyEmbedder()
    return _embedder
