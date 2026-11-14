"""Sanitize, restructure, and deduplicate the extracted VELOCITYMEDIA/INFLUENCE corpus."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.cleaners import format_clean_markdown, is_meaningful_doc


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prune_empty_dirs(root: Path) -> None:
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            next(d.iterdir())
        except StopIteration:
            d.rmdir()


def sanitize_pilot(hub_root: Path) -> dict[str, Any]:
    vel_root = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / "VELOCITYMEDIA"
    inf_root = vel_root / "INFLUENCE"
    disc_file = hub_root / "02_INDICE_POR_DISCIPLINA" / "99_descartados_fuera_de_alcance.json"
    manifest_path = hub_root / "06_MANIFIESTOS" / "manifest.json"
    old_manifest = json.loads(manifest_path.read_text(encoding="utf-8")).get("items", {})

    discarded_paths = {x["path"] for x in json.loads(disc_file.read_text(encoding="utf-8"))}

    # 1. Remove discarded academic/stub files and move valid root NotebookLM sources into subfolder
    ext_dir = inf_root / "00_fuentes_externas_notebooklm"
    ext_dir.mkdir(parents=True, exist_ok=True)
    removed_discarded = 0
    moved_external = 0

    for md in list(inf_root.glob("*.md")):
        rel_old = str(md.relative_to(vel_root))
        if rel_old in discarded_paths:
            md.unlink()
            removed_discarded += 1
            continue
        dest = ext_dir / md.name
        shutil.move(str(md), str(dest))
        if rel_old in old_manifest:
            old_manifest[str(dest.relative_to(vel_root))] = old_manifest.pop(rel_old)
        moved_external += 1

    # 2. Re-sanitize every remaining .md file and remove tiny stubs
    resanitized = 0
    removed_tiny = 0
    for md in sorted(vel_root.rglob("*.md")):
        raw = md.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        title = lines[0] if lines else md.stem
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        cleaned = format_clean_markdown(title, body)
        if not is_meaningful_doc(cleaned, min_body_chars=250):
            md.unlink()
            removed_tiny += 1
            continue
        if cleaned != raw:
            md.write_text(cleaned, encoding="utf-8")
            resanitized += 1

    # 3. Deduplicate exact body SHA256s (preferring non-04_cohortes canonical folders)
    def _sort_key(p: Path) -> tuple[int, str]:
        rel = str(p.relative_to(vel_root))
        # Keep 01_cursos before 04_cohortes, numbered lesson names cleanly
        priority = 1 if "04_cohortes/" in rel else 0
        return (priority, rel)

    seen_hashes: dict[str, str] = {}
    dedup_removed: list[dict[str, str]] = []
    for md in sorted(vel_root.rglob("*.md"), key=_sort_key):
        raw = md.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        body = "\n".join(lines[1:]).strip()
        h = sha256_text(body)
        rel = str(md.relative_to(vel_root))
        if h in seen_hashes:
            md.unlink()
            dedup_removed.append({"removed": rel, "canonical": seen_hashes[h]})
        else:
            seen_hashes[h] = rel

    _prune_empty_dirs(vel_root)

    # 4. Rebuild clean manifest strictly matching surviving files on disk
    new_items: dict[str, Any] = {}
    for md in sorted(vel_root.rglob("*.md")):
        rel = str(md.relative_to(vel_root))
        text = md.read_text(encoding="utf-8", errors="ignore")
        meta = dict(old_manifest.get(rel, {}))
        curso = rel.split("/")[0] if "/" in rel else "VELOCITYMEDIA"
        # Preserve disciplina/tipo where classified; assign prompt tipo cleanly to 09_biblioteca_prompts
        disciplina = meta.get("disciplina", "")
        tipo = meta.get("tipo", "lesson")
        if "09_biblioteca_prompts/" in rel:
            tipo = "prompt"
        elif "05_playbooks/" in rel:
            tipo = "framework"
        new_items[rel] = {
            "academia": "VELOCITYMEDIA",
            "curso": curso,
            "source_path": meta.get("source_path", f"CURSOS/VELOCITYMEDIA/{rel}"),
            "source_ext": meta.get("source_ext", ".md"),
            "extractor": meta.get("extractor", "sanitized"),
            "disciplina": disciplina,
            "tipo": tipo,
            "sha256": sha256_text(text),
            "chars": len(text),
        }

    manifest_path.write_text(
        json.dumps({"items": new_items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (hub_root / "06_MANIFIESTOS" / "deduplicated_aliases.json").write_text(
        json.dumps(dedup_removed, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "removed_discarded": removed_discarded,
        "moved_external": moved_external,
        "removed_tiny": removed_tiny,
        "resanitized": resanitized,
        "dedup_removed": len(dedup_removed),
        "surviving_files": len(new_items),
        "missing_disciplina": sum(1 for v in new_items.values() if not v.get("disciplina")),
    }


if __name__ == "__main__":
    out = sanitize_pilot(Path("/var/www/localstorage/knowledge_hub"))
    print(json.dumps(out, ensure_ascii=False))
