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
    """Search clean marketing, sales, copywriting, and strategy knowledge in Qdrant."""
    bounded_limit = max(1, min(limit, 25))
    return get_store().search(
        query=query,
        limit=bounded_limit,
        academia=academia,
        disciplina=disciplina,
        tipo=tipo,
    )


@mcp.tool()
def get_hub_stats() -> dict[str, Any]:
    """Return Qdrant collection status and indexed chunk count."""
    return get_store().stats()
