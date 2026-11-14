"""Deterministic $0 cleaners for WebVTT subtitles, PDF, DOCX, and clean Markdown."""

import re
from pathlib import Path

_VTT_HEADER_RE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\b).*$", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}.*$"
)
_CUE_INDEX_RE = re.compile(r"^\s*\d+\s*$")
_INLINE_TAG_RE = re.compile(r"<[^>]+>")
_NLM_IMG_URL_RE = re.compile(
    r"^\s*https://lh3\.googleusercontent\.com/notebooklm/\S+\s*$", re.MULTILINE
)
_STANDALONE_UUID_RE = re.compile(
    r"^\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PDF_FONT_LINE_RE = re.compile(
    r"^\s*(?:[A-Za-z0-9_]+-(?:Thin|ExtraLight|Light|Regular|Medium|SemiBold|Bold|ExtraBold|Black|Heavy|Italic|Oblique|Lt|Md|Bd|Rg|Bk)\b[A-Za-z0-9_-]*|NHaasGrotesk[A-Za-z0-9_-]+)\s*$"
)


def _collapse_spaced_line(line: str) -> str:
    """Collapse PDF spaced-letter typography lines like 'I N F L U E N C E' -> 'INFLUENCE'."""
    stripped = line.strip()
    if not stripped:
        return line
    tokens = stripped.split(" ")
    single_tokens = sum(1 for t in tokens if len(t) == 1 and t.isalnum())
    if len(tokens) >= 4 and single_tokens / len(tokens) >= 0.7:
        collapsed = re.sub(
            r"(?<=\b[A-Za-zÁÉÍÓÚÑÜ0-9]) (?=[A-Za-zÁÉÍÓÚÑÜ0-9]\b)", "", stripped
        )
        return re.sub(r"\s{2,}", " ", collapsed)
    return line


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
            lines[-1] = norm
        else:
            lines.append(norm)
        prev_norm = norm
    return "\n".join(lines).strip()


def format_clean_markdown(title: str, body: str) -> str:
    """Format lesson Markdown strictly with single # Title and sanitized body (zero PDF/NLM bloat)."""
    stripped = _NLM_IMG_URL_RE.sub("", body)
    stripped = _STANDALONE_UUID_RE.sub("", stripped)

    cleaned_lines: list[str] = []
    for raw_line in stripped.splitlines():
        if _PDF_FONT_LINE_RE.match(raw_line):
            continue
        cleaned_lines.append(_collapse_spaced_line(raw_line))

    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)

    clean_title = " ".join(title.strip().lstrip("#").split()) or "Untitled"
    # Avoid double H1 if source body already begins with a descriptive Markdown H1 heading
    if cleaned_lines and cleaned_lines[0].lstrip().startswith("# "):
        existing_h1 = " ".join(cleaned_lines[0].lstrip()[2:].split())
        if existing_h1:
            clean_title = existing_h1
            cleaned_lines.pop(0)
            while cleaned_lines and not cleaned_lines[0].strip():
                cleaned_lines.pop(0)

    clean_body = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines).strip())
    return f"# {clean_title}\n\n{clean_body}\n" if clean_body else f"# {clean_title}\n"


def is_meaningful_doc(md_text: str, min_body_chars: int = 300) -> bool:
    """Return True when document has substantive body content beyond title stubs."""
    lines = [l for l in md_text.splitlines() if l.strip()]
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    return len(body) >= min_body_chars


def extract_pdf_text(path: str | Path) -> str:
    """Extract text from a PDF file using pypdf (handles empty-password AES PDFs)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p.strip() for p in pages if p.strip())
    except Exception:
        return ""


def extract_docx_text(path: str | Path) -> str:
    """Extract paragraph text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(str(path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(paras)
