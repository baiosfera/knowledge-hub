"""Markdown chunker for Qdrant vector indexing."""

from typing import Any


def chunk_markdown(
    title: str,
    body: str,
    max_chars: int = 900,
    overlap: int = 150,
    academia: str = "",
    curso: str = "",
    disciplina: str = "",
    tipo: str = "lesson",
    path: str = "",
    source_sha256: str = "",
) -> list[dict[str, Any]]:
    """Split clean Markdown body into overlapping paragraph-aware chunks."""
    clean_body = body.strip()
    if not clean_body:
        return []

    paragraphs = [p.strip() for p in clean_body.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            step = max(1, max_chars - overlap)
            while start < len(para):
                chunks.append(para[start : start + max_chars].strip())
                start += step
            continue

        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap:].strip() if overlap > 0 and len(current) > overlap else ""
            current = f"{tail}\n\n{para}".strip() if tail else para

    if current:
        chunks.append(current)

    return [
        {
            "title": title,
            "text": text,
            "academia": academia,
            "curso": curso,
            "disciplina": disciplina,
            "tipo": tipo,
            "path": path,
            "source_sha256": source_sha256,
            "chunk_index": idx,
        }
        for idx, text in enumerate(chunks)
    ]
