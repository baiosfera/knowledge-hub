"""Unit tests for deterministic cleaners and word-safe Markdown chunker."""

from scripts.chunker import chunk_markdown
from scripts.cleaners import clean_webvtt_text, format_clean_markdown, is_meaningful_doc


def test_clean_webvtt_strips_headers_tags_and_rolling_duplicates():
    raw = """WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:03.000
Hola<00:00:01.500><c> emprendedores</c>

00:00:03.000 --> 00:00:05.000
Hola emprendedores bienvenidos al curso

00:00:05.000 --> 00:00:07.000
Hoy veremos posicionamiento
"""
    cleaned = clean_webvtt_text(raw)
    assert cleaned == "Hola emprendedores bienvenidos al curso\nHoy veremos posicionamiento"


def test_format_clean_markdown_strips_fonts_spaced_caps_double_h1_and_watermarks():
    body = (
        "# Combinar dos competencias clave\n\n"
        "I N F L U E N C E\n\n"
        "Poppins-Light\n\n"
        "NHaasGroteskDSW01-45Lt\n\n"
        "Primer párrafo.\n\n"
        "https://lh3.googleusercontent.com/notebooklm/ABzcPv3kuz=w70-h60-v0\n\n\n"
        "Segundo párrafo.\n\n"
        "8a887473-a2f6-40ea-8085-73f2a2b47db4"
    )
    md = format_clean_markdown("015_slug_feo", body)
    assert md == (
        "# Combinar dos competencias clave\n\n"
        "INFLUENCE\n\n"
        "Primer párrafo.\n\n"
        "Segundo párrafo.\n"
    )


def test_is_meaningful_doc_filters_tiny_stubs():
    assert not is_meaningful_doc("# Title\n\nTiny stub\n")
    assert is_meaningful_doc("# Title\n\n" + ("Contenido sustancial. " * 25))


def test_chunk_markdown_respects_word_boundaries_and_adds_context_header():
    long_para = " ".join(f"palabra{i}" for i in range(180))
    body = f"## Módulo A\n\n{long_para}"
    chunks = chunk_markdown(
        title="Category of One",
        body=body,
        max_chars=450,
        overlap=80,
        academia="VELOCITYMEDIA",
        curso="INFLUENCE",
        disciplina="posicionamiento",
        tipo="playbook",
        path="03_PLAYBOOKS_MAESTROS/00_category_of_one.md",
        source_sha256="abc123",
    )
    assert len(chunks) >= 2
    for idx, ch in enumerate(chunks):
        assert ch["chunk_index"] == idx
        assert ch["text"].startswith("[Category of One > Módulo A]\n")
        content_after_hdr = ch["text"].split("\n", 1)[1]
        # Ensure first token after header is a whole word (starts with 'palabra' or '##')
        first_word = content_after_hdr.split()[0]
        assert first_word.startswith("palabra") or first_word.startswith("##")
