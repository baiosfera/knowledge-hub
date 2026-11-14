"""FastMCP server exposing Baiosfera Knowledge Hub tools over Streamable HTTP."""

from typing import Any
from fastmcp import FastMCP

from app.qdrant_store import get_store

mcp = FastMCP("baiosfera-knowledge-hub")


@mcp.tool()
def search_knowledge(
    query: str,
    limit: int = 8,
    academia: str | None = None,
    disciplina: str | None = None,
    tipo: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over Playbooks, Tactical Banks, and Lessons (diversified per source).
    Filter `tipo` with 'playbook', 'tactical_bank', 'prompt', 'framework', or 'lesson'.
    """
    bounded_limit = max(1, min(limit, 25))
    return get_store().search(
        query=query,
        limit=bounded_limit,
        academia=academia,
        disciplina=disciplina,
        tipo=tipo,
        max_per_source=2,
    )


@mcp.tool()
def list_curated_assets() -> list[dict[str, str]]:
    """List all indexed universal Playbooks ({{SLOT_*}}) and Tactical Banks (prompts/swipes)."""
    return get_store().list_curated_assets()


@mcp.tool()
def get_document(path: str) -> dict[str, Any]:
    """Retrieve a complete Playbook, Tactical Bank, prompt, or lesson by exact `path`."""
    doc = get_store().get_document(path)
    if not doc:
        return {"error": f"Document not found: {path}"}
    return doc


@mcp.tool()
def get_hub_stats() -> dict[str, Any]:
    """Return Qdrant collection status and indexed chunk count."""
    return get_store().stats()
