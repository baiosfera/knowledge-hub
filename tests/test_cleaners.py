"""Unit tests for deterministic cleaners and Markdown chunker."""

from scripts.chunker import chunk_markdown
from scripts.cleaners import clean_webvtt_text, format_clean_markdown


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


def test_format_clean_markdown_zero_metadata_bloat():
    body = (
        "Primer párrafo.\n\n"
        "https://lh3.googleusercontent.com/notebooklm/ABzcPv3kuz=w70-h60-v0\n\n\n"
        "Segundo párrafo.\n\n"
        "8a887473-a2f6-40ea-8085-73f2a2b47db4"
    )
    md = format_clean_markdown("  # Clase 1: Fundamentos  ", body)
    assert md == "# Clase 1: Fundamentos\n\nPrimer párrafo.\n\nSegundo párrafo.\n"


def test_chunk_markdown_splits_and_attaches_payload_fields():
    body = ("Párrafo de prueba número uno. " * 25) + "\n\n" + ("Párrafo de prueba número dos. " * 25)
    chunks = chunk_markdown(
        title="Lección 1",
        body=body,
        max_chars=500,
        overlap=80,
        academia="VELOCITYMEDIA",
        curso="INFLUENCE",
        disciplina="posicionamiento",
        tipo="lesson",
        path="01_TRANSCRIPCIONES_LIMPIAS/VELOCITYMEDIA/INFLUENCE/01.md",
        source_sha256="abc123",
    )
    assert len(chunks) >= 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[1]["chunk_index"] == 1
    assert chunks[0]["academia"] == "VELOCITYMEDIA"
    assert chunks[0]["disciplina"] == "posicionamiento"
