"""Hierarchical, word-boundary Markdown chunker for Qdrant vector indexing."""

import re
from typing import Any


def _word_boundary_tail(text: str, max_chars: int) -> str:
    """Return a clean trailing overlap slice starting on a word boundary."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text.strip()
    slice_start = len(text) - max_chars
    m = re.search(r"\s+\S", text[slice_start:])
    if m:
        return text[slice_start + m.start() :].strip()
    return ""


def _split_long_paragraph(para: str, max_chars: int, overlap: int) -> list[str]:
    """Split an oversized paragraph strictly at sentence/word boundaries."""
    words = para.split()
    pieces: list[str] = []
    cur_words: list[str] = []
    cur_len = 0

    for word in words:
        wlen = len(word) + (1 if cur_words else 0)
        if cur_len + wlen <= max_chars or not cur_words:
            cur_words.append(word)
            cur_len += wlen
        else:
            chunk = " ".join(cur_words)
            pieces.append(chunk)
            tail = _word_boundary_tail(chunk, overlap)
            cur_words = (tail.split() + [word]) if tail else [word]
            cur_len = sum(len(w) for w in cur_words) + max(0, len(cur_words) - 1)

    if cur_words:
        pieces.append(" ".join(cur_words))
    return pieces


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
    """Split clean Markdown body into word-safe overlapping chunks with hierarchical context."""
    clean_body = body.strip()
    if not clean_body:
        return []

    paragraphs = [p.strip() for p in clean_body.split("\n\n") if p.strip()]
    raw_chunks: list[tuple[str, str]] = []
    current = ""
    current_section = ""

    for para in paragraphs:
        if para.startswith("## ") or para.startswith("### "):
            current_section = para.splitlines()[0].lstrip("#").strip()

        header_prefix = f"[{title}" + (f" > {current_section}]" if current_section else "]")
        effective_max = max(250, max_chars - len(header_prefix) - 2)

        if len(para) > effective_max:
            if current:
                raw_chunks.append((header_prefix, current))
                current = ""
            for sub in _split_long_paragraph(para, effective_max, overlap):
                raw_chunks.append((header_prefix, sub))
            continue

        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= effective_max:
            current = candidate
        else:
            raw_chunks.append((header_prefix, current))
            tail = _word_boundary_tail(current, overlap)
            if tail and len(tail) + len(para) + 2 <= effective_max:
                current = f"{tail}\n\n{para}".strip()
            else:
                current = para

    if current:
        header_prefix = f"[{title}" + (f" > {current_section}]" if current_section else "]")
        raw_chunks.append((header_prefix, current))

    return [
        {
            "title": title,
            "text": f"{hdr}\n{chunk_body}",
            "academia": academia,
            "curso": curso,
            "disciplina": disciplina,
            "tipo": tipo,
            "path": path,
            "source_sha256": source_sha256,
            "chunk_index": idx,
        }
        for idx, (hdr, chunk_body) in enumerate(raw_chunks)
    ]
