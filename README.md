# Baiosfera Knowledge Hub

Sovereign knowledge extraction, clean Markdown corpus compiler, DeepSeek playbook distiller, and portable Qdrant + FastMCP service (`ubuntu/python@3.12` + `qdrant:single@1.12`).

## Endpoints

- `GET /health` — Unauthenticated liveness probe.
- `GET /v1/stats` — Collection statistics (Bearer token required).
- `POST /v1/search` — Semantic search with optional `academia`, `curso`, `disciplina`, `tipo` filters (Bearer token required).
- `POST /v1/index` — Idempotent chunk upsert (Bearer token required).
- `POST /v1/snapshot` — Trigger portable Qdrant snapshot (Bearer token required).
- `POST /mcp` — Streamable HTTP FastMCP server (`search_knowledge`, `get_hub_stats`) (Bearer token required).
