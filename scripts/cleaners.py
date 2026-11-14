"""Deterministic $0 cleaners for WebVTT subtitles, PDF, DOCX, and clean Markdown."""

import re
from pathlib import Path

_VTT_HEADER_RE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\b).*$", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}.*$"
)
_CUE_INDEX_RE = re.compile(r"^\s*\d+\s*$")
_INLINE_TAG_RE = re.compile(r"<[^>]+>")


def clean_webvtt_text(raw: str) -> str:
    """Strip WebVTT/SRT timestamps, tags, and deduplicate rolling YouTube captions."""
    lines: list[str] = []
    prev_norm = ""
    for raw_line in raw.splitlines():
        line = _INLINE_TAG_RE.sub("", raw_line).strip()
        if not line:
            continue
        if _VTT_HEADER_RE.match(line) or _TIMESTAMP_RE.match(line) or _CUE_INDEX_RE.match(line):
            continue
        norm = " ".join(line.split())
        if not norm or norm == prev_norm:
            continue
        if prev_norm and norm.startswith(prev_norm):
            # Rolling caption repeats previous line + new suffix; replace previous line
            lines[-1] = norm
        else:
            lines.append(norm)
        prev_norm = norm
    return "\n".join(lines).strip()


def format_clean_markdown(title: str, body: str) -> str:
    """Format lesson Markdown strictly with # Title and clean body (zero metadata bloat)."""
    clean_title = " ".join(title.strip().lstrip("#").split()) or "Untitled"
    clean_body = re.sub(r"\n{3,}", "\n\n", body.strip())
    return f"# {clean_title}\n\n{clean_body}\n" if clean_body else f"# {clean_title}\n"


def extract_pdf_text(path: str | Path) -> str:
    """Extract text from a PDF file using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def extract_docx_text(path: str | Path) -> str:
    """Extract paragraph text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(str(path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(paras)
