"""FastAPI entrypoint for Baiosfera Knowledge Hub (/health, /v1/*, /mcp)."""

from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import require_bearer, verify_bearer_token
from app.mcp_server import mcp
from app.qdrant_store import get_store

mcp_app = mcp.http_app(path="/", stateless_http=True)

app = FastAPI(
    title="Baiosfera Knowledge Hub",
    version="0.1.0",
    lifespan=mcp_app.lifespan,
)


@app.middleware("http")
async def mcp_bearer_guard(request: Request, call_next):
    """Enforce Bearer authentication on the mounted /mcp endpoint."""
    if request.url.path.startswith("/mcp"):
        try:
            verify_bearer_token(request.headers.get("authorization"))
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or {},
            )
    return await call_next(request)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=8, ge=1, le=25)
    academia: str | None = None
    curso: str | None = None
    disciplina: str | None = None
    tipo: str | None = None


class ChunkInput(BaseModel):
    title: str = ""
    text: str = Field(..., min_length=1)
    academia: str = ""
    curso: str = ""
    disciplina: str = ""
    tipo: str = "lesson"
    path: str = ""
    source_sha256: str = ""
    chunk_index: int = 0


class IndexRequest(BaseModel):
    chunks: list[ChunkInput] = Field(..., min_length=1, max_length=256)


@app.get("/")
def root() -> dict[str, Any]:
    """Public service metadata and endpoint index."""
    return {
        "status": "ok",
        "service": "baiosfera-knowledge-hub",
        "endpoints": ["/health", "/v1/stats", "/v1/search", "/v1/index", "/v1/snapshot", "/mcp"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Unauthenticated liveness probe."""
    return {"status": "ok", "service": "baiosfera-knowledge-hub"}


@app.get("/v1/stats", dependencies=[Depends(require_bearer)])
def stats() -> dict[str, Any]:
    """Return Qdrant collection statistics."""
    return get_store().stats()


@app.post("/v1/search", dependencies=[Depends(require_bearer)])
def search(req: SearchRequest) -> dict[str, Any]:
    """Semantic search over indexed knowledge chunks."""
    results = get_store().search(
        query=req.query,
        limit=req.limit,
        academia=req.academia,
        curso=req.curso,
        disciplina=req.disciplina,
        tipo=req.tipo,
    )
    return {"query": req.query, "count": len(results), "results": results}


@app.post("/v1/index", dependencies=[Depends(require_bearer)])
def index_chunks(req: IndexRequest) -> dict[str, int]:
    """Upsert pre-chunked documents into Qdrant."""
    upserted = get_store().upsert_chunks([c.model_dump() for c in req.chunks])
    return {"upserted": upserted}


@app.post("/v1/snapshot", dependencies=[Depends(require_bearer)])
def snapshot() -> dict[str, str]:
    """Create a portable Qdrant snapshot for project migration."""
    name = get_store().create_snapshot()
    return {"snapshot": name}


app.mount("/mcp", mcp_app)
