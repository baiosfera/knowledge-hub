"""Index clean .md corpus, playbooks, and tactical banks into Knowledge Hub (/v1/index)."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx

from scripts.chunker import chunk_markdown


def index_hub(hub_root: Path, base_url: str, token: str, batch_size: int = 16) -> dict[str, Any]:
    manifest_path = hub_root / "06_MANIFIESTOS" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", {})

    all_chunks: list[dict[str, Any]] = []
    files_indexed = 0

    for rel_path, meta in items.items():
        if meta.get("disciplina") == "descartar_fuera_de_alcance":
            continue
        md_file = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / meta["academia"] / rel_path
        if not md_file.exists():
            continue
        raw = md_file.read_text(encoding="utf-8", errors="ignore").strip()
        lines = raw.splitlines()
        title = lines[0].lstrip("#").strip() if lines else md_file.stem
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
        chunks = chunk_markdown(
            title=title,
            body=body,
            academia=meta.get("academia", ""),
            curso=meta.get("curso", ""),
            disciplina=meta.get("disciplina", "negocio_mentalidad"),
            tipo=meta.get("tipo", "lesson"),
            path=f"01_TRANSCRIPCIONES_LIMPIAS/{meta['academia']}/{rel_path}",
            source_sha256=meta.get("sha256", ""),
        )
        all_chunks.extend(chunks)
        files_indexed += 1

    for folder, tipo, disc in (
        ("03_PLAYBOOKS_MAESTROS", "playbook", "posicionamiento"),
        ("04_BANCOS_TACTICOS", "tactical_bank", "posicionamiento"),
    ):
        for md_file in sorted((hub_root / folder).glob("*.md")):
            raw = md_file.read_text(encoding="utf-8", errors="ignore").strip()
            lines = raw.splitlines()
            title = lines[0].lstrip("#").strip() if lines else md_file.stem
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
            sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            all_chunks.extend(
                chunk_markdown(
                    title=title,
                    body=body,
                    academia="BAIOSFERA",
                    curso=folder,
                    disciplina=disc,
                    tipo=tipo,
                    path=f"{folder}/{md_file.name}",
                    source_sha256=sha,
                )
            )
            files_indexed += 1

    upserted = 0
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=120.0) as client:
        for idx in range(0, len(all_chunks), batch_size):
            batch = all_chunks[idx : idx + batch_size]
            resp = client.post(f"{base_url.rstrip('/')}/v1/index", headers=headers, json={"chunks": batch})
            resp.raise_for_status()
            upserted += resp.json().get("upserted", 0)

    return {"files_indexed": files_indexed, "chunks_sent": len(all_chunks), "upserted": upserted}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://knowledge-278-8000.ny1.zerops.app")
    args = parser.parse_args()

    token = os.environ.get("KNOWLEDGE_BEARER_TOKEN", "").strip()
    if not token:
        raise SystemExit("KNOWLEDGE_BEARER_TOKEN is required")
    res = index_hub(Path("/var/www/localstorage/knowledge_hub"), args.url, token)
    print(json.dumps(res))
