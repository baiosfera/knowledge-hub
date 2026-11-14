"""Disposable NotebookLM $0 audio extractor and source harvester."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from threading import Lock
from typing import Any

from scripts.cleaners import extract_docx_text, extract_pdf_text, format_clean_markdown

RCLONE_BIN = "/var/www/.rclone/bin/rclone"
RCLONE_CFG = "/var/www/.rclone/config/rclone/rclone.conf"


def run_cmd(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\d+[_.]\s*", "", stem)
    return re.sub(r"[^a-z0-9]+", "", stem.lower())


def load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"items": {}}


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def harvest_notebook_sources(
    notebook_id: str,
    sources_json: Path,
    drive_index: list[dict[str, Any]],
    out_root: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    default_subdir: str,
) -> tuple[int, int]:
    """Harvest already-ingested NotebookLM sources into clean # Title + body .md files."""
    sources = json.loads(sources_json.read_text(encoding="utf-8"))
    by_exact = {Path(x["Path"]).name: x for x in drive_index if not x.get("IsDir")}
    by_norm = {normalize_stem(Path(x["Path"]).name): x for x in drive_index if not x.get("IsDir")}

    harvested = 0
    skipped = 0
    seen_norms: set[str] = set()

    for src in sources:
        src_id = src["id"]
        title = src.get("title", "").strip()
        norm = normalize_stem(title)
        if not title or norm in seen_norms:
            skipped += 1
            continue
        seen_norms.add(norm)

        match = by_exact.get(title) or by_norm.get(norm)
        if match:
            rel_drive_path = match["Path"]
            rel_md_path = str(Path(rel_drive_path).with_suffix(".md"))
            curso = rel_drive_path.split("/")[0] if "/" in rel_drive_path else default_subdir
        else:
            safe_name = re.sub(r'[<>:"/\\|?*]+', "_", Path(title).stem).strip() or src_id
            rel_drive_path = f"{default_subdir}/{title}"
            rel_md_path = f"{default_subdir}/{safe_name}.md"
            curso = default_subdir

        out_file = out_root / rel_md_path
        if rel_md_path in manifest["items"] and out_file.exists():
            skipped += 1
            continue

        proc = run_cmd(["nlm", "source", "content", src_id, "--json"], timeout=60)
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue

        body = (payload.get("value") or {}).get("content") or payload.get("content") or ""
        if not isinstance(body, str) or len(body.strip()) < 40:
            continue

        clean_title = Path(title).stem
        md_text = format_clean_markdown(clean_title, body)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(md_text, encoding="utf-8")

        manifest["items"][rel_md_path] = {
            "academia": "VELOCITYMEDIA",
            "curso": curso,
            "source_path": f"CURSOS/VELOCITYMEDIA/{rel_drive_path}",
            "source_ext": Path(title).suffix.lower(),
            "extractor": f"nlm_harvest:{notebook_id[:8]}",
            "sha256": sha256_text(md_text),
            "chars": len(md_text),
        }
        harvested += 1
        if harvested % 10 == 0:
            save_manifest(manifest_path, manifest)

    save_manifest(manifest_path, manifest)
    return harvested, skipped


def upload_and_extract_audio(
    notebook_id: str,
    local_audio: Path,
    title: str,
) -> str | None:
    """Upload one audio file to a disposable NotebookLM buffer and extract its transcript."""
    add_proc = run_cmd(
        [
            "nlm",
            "source",
            "add",
            notebook_id,
            "--file",
            str(local_audio),
            "--wait",
            "--wait-timeout",
            "600",
        ],
        timeout=630,
    )
    if add_proc.returncode != 0:
        return None

    list_proc = run_cmd(["nlm", "source", "list", notebook_id, "--json"], timeout=60)
    if list_proc.returncode != 0:
        return None
    sources = json.loads(list_proc.stdout)
    target_norm = normalize_stem(local_audio.name)
    src_id = None
    for s in reversed(sources):
        if s.get("title") == local_audio.name or normalize_stem(s.get("title", "")) == target_norm:
            src_id = s["id"]
            break
    if not src_id:
        return None

    content_proc = run_cmd(["nlm", "source", "content", src_id, "--json"], timeout=60)
    if content_proc.returncode != 0 or not content_proc.stdout.strip():
        return None
    payload = json.loads(content_proc.stdout)
    body = (payload.get("value") or {}).get("content") or payload.get("content") or ""
    if not isinstance(body, str) or len(body.strip()) < 20:
        return None
    return format_clean_markdown(title, body)


def ensure_buffer_notebook(title: str) -> str:
    """Find or create a disposable NotebookLM buffer notebook."""
    proc = run_cmd(["nlm", "notebook", "list", "--json"], timeout=60)
    if proc.returncode == 0:
        for nb in json.loads(proc.stdout):
            if nb.get("title") == title and int(nb.get("source_count") or 0) < 250:
                return nb["id"]
    create_proc = run_cmd(["nlm", "notebook", "create", title, "--json"], timeout=60)
    if create_proc.returncode == 0 and create_proc.stdout.strip():
        try:
            data = json.loads(create_proc.stdout)
            nb_id = data.get("id") or data.get("notebook_id") or (data.get("notebook") or {}).get("id")
            if nb_id:
                return nb_id
        except json.JSONDecodeError:
            pass
    proc2 = run_cmd(["nlm", "notebook", "list", "--json"], timeout=60)
    for nb in json.loads(proc2.stdout):
        if nb.get("title") == title and int(nb.get("source_count") or 0) < 250:
            return nb["id"]
    raise RuntimeError(f"Unable to create or locate buffer notebook {title}")


def extract_pending_velocity(
    drive_index_path: Path,
    out_root: Path,
    manifest_path: Path,
    max_audios: int = 0,
    harvest_only: bool = False,
    docs_only: bool = False,
    prefix: str = "",
    workers: int = 6,
) -> None:
    drive_index = json.loads(drive_index_path.read_text(encoding="utf-8"))
    manifest = load_manifest(manifest_path)

    if harvest_only:
        h1, s1 = harvest_notebook_sources(
            "63f2b7ea-bfce-482b-add5-02997157cb47",
            manifest_path.parent / "nlm_coo.json",
            drive_index,
            out_root,
            manifest,
            manifest_path,
            "INFLUENCE",
        )
        h2, s2 = harvest_notebook_sources(
            "3e5ebc18-19e9-4e35-a5ad-6c99c9bb9aca",
            manifest_path.parent / "nlm_midas.json",
            drive_index,
            out_root,
            manifest,
            manifest_path,
            "1.MIDAS",
        )
        print(json.dumps({"coo_harvested": h1, "coo_skipped": s1, "midas_harvested": h2, "midas_skipped": s2}))
        return

    stage_dir = Path("/tmp/nlm_stage")
    stage_dir.mkdir(parents=True, exist_ok=True)

    # First extract all deterministic PDF/DOCX/MD/TXT not yet in manifest
    docs_done = 0
    pending_audios: list[dict[str, Any]] = []
    for item in drive_index:
        if item.get("IsDir"):
            continue
        rel_path = item["Path"]
        ext = Path(rel_path).suffix.lower()
        if "/AGY/" in f"/{rel_path}" or ext in (".json", ".py", ".sh"):
            continue
        if Path(rel_path).name == "Resources.md" and item.get("Size", 0) < 1024:
            continue

        rel_md = str(Path(rel_path).with_suffix(".md"))
        out_file = out_root / rel_md
        if rel_md in manifest["items"] and out_file.exists():
            continue

        if ext == ".m4a":
            pending_audios.append(item)
            continue

        if ext in (".pdf", ".docx", ".md", ".txt"):
            # Skip if an .m4a with same stem already produced this .md
            if out_file.exists():
                continue
            local_tmp = stage_dir / Path(rel_path).name
            dl = run_cmd([RCLONE_BIN, "--config", RCLONE_CFG, "copyto", f"baiosfera:CURSOS/VELOCITYMEDIA/{rel_path}", str(local_tmp)], timeout=120)
            if dl.returncode != 0 or not local_tmp.exists():
                continue
            try:
                if ext == ".pdf":
                    body = extract_pdf_text(local_tmp)
                elif ext == ".docx":
                    body = extract_docx_text(local_tmp)
                else:
                    body = local_tmp.read_text(encoding="utf-8", errors="ignore")
            finally:
                local_tmp.unlink(missing_ok=True)
            if len(body.strip()) < 40:
                continue
            md_text = format_clean_markdown(Path(rel_path).stem, body)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(md_text, encoding="utf-8")
            manifest["items"][rel_md] = {
                "academia": "VELOCITYMEDIA",
                "curso": rel_path.split("/")[0] if "/" in rel_path else "VELOCITYMEDIA",
                "source_path": f"CURSOS/VELOCITYMEDIA/{rel_path}",
                "source_ext": ext,
                "extractor": f"deterministic_{ext.lstrip('.')}",
                "sha256": sha256_text(md_text),
                "chars": len(md_text),
            }
            docs_done += 1
            if docs_done % 10 == 0:
                save_manifest(manifest_path, manifest)

    save_manifest(manifest_path, manifest)
    if docs_only:
        print(json.dumps({"docs_done": docs_done, "pending_audios_total": len(pending_audios)}))
        return

    if prefix:
        pending_audios = [x for x in pending_audios if x["Path"].startswith(prefix)]

    audios_done = 0
    audios_failed = 0
    limit = max_audios if max_audios > 0 else len(pending_audios)
    batch_items = pending_audios[:limit]
    lock = Lock()

    # Pre-allocate buffer notebooks (max ~240 sources each)
    nb_ids: list[str] = []
    num_nbs = max(1, (len(batch_items) + 239) // 240)
    for idx in range(1, num_nbs + 1):
        nb_ids.append(ensure_buffer_notebook(f"[BUFFER_WHISPER_{idx:02d}]"))

    def _process_one(idx: int, item: dict[str, Any]) -> bool:
        rel_path = item["Path"]
        rel_md = str(Path(rel_path).with_suffix(".md"))
        out_file = out_root / rel_md
        with lock:
            if rel_md in manifest["items"] and out_file.exists():
                return True

        nb_id = nb_ids[idx // 240]
        local_tmp = stage_dir / f"{idx}_{Path(rel_path).name}"
        dl = run_cmd(
            [RCLONE_BIN, "--config", RCLONE_CFG, "copyto", f"baiosfera:CURSOS/VELOCITYMEDIA/{rel_path}", str(local_tmp)],
            timeout=180,
        )
        if dl.returncode != 0 or not local_tmp.exists():
            return False

        try:
            md_text = upload_and_extract_audio(nb_id, local_tmp, Path(rel_path).stem)
        finally:
            local_tmp.unlink(missing_ok=True)

        if not md_text:
            return False

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(md_text, encoding="utf-8")
        with lock:
            manifest["items"][rel_md] = {
                "academia": "VELOCITYMEDIA",
                "curso": rel_path.split("/")[0] if "/" in rel_path else "VELOCITYMEDIA",
                "source_path": f"CURSOS/VELOCITYMEDIA/{rel_path}",
                "source_ext": ".m4a",
                "extractor": f"nlm_whisper:{nb_id[:8]}",
                "sha256": sha256_text(md_text),
                "chars": len(md_text),
            }
            save_manifest(manifest_path, manifest)
        return True

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_process_one, idx, item): item for idx, item in enumerate(batch_items)}
        for fut in as_completed(futures):
            try:
                if fut.result():
                    audios_done += 1
                else:
                    audios_failed += 1
            except Exception:
                audios_failed += 1

    print(
        json.dumps(
            {
                "docs_done": docs_done,
                "pending_audios_total": len(pending_audios),
                "audios_done": audios_done,
                "audios_failed": audios_failed,
            }
        )
    )
    sync_to_drive(Path("/var/www/localstorage/knowledge_hub"))


def sync_to_drive(hub_root: Path) -> None:
    """Mirror local staging KNOWLEDGE_HUB/ to Google Drive baiosfera:KNOWLEDGE_HUB/."""
    run_cmd([RCLONE_BIN, "--config", RCLONE_CFG, "copy", str(hub_root), "baiosfera:KNOWLEDGE_HUB", "--transfers", "8"], timeout=600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--harvest-only", action="store_true")
    parser.add_argument("--docs-only", action="store_true")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--max-audios", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    extract_pending_velocity(
        drive_index_path=Path("/var/www/localstorage/knowledge_hub/06_MANIFIESTOS/drive_velocitymedia.json"),
        out_root=Path("/var/www/localstorage/knowledge_hub/01_TRANSCRIPCIONES_LIMPIAS/VELOCITYMEDIA"),
        manifest_path=Path("/var/www/localstorage/knowledge_hub/06_MANIFIESTOS/manifest.json"),
        max_audios=args.max_audios,
        harvest_only=args.harvest_only,
        docs_only=args.docs_only,
        prefix=args.prefix,
        workers=args.workers,
    )
