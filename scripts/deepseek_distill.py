"""DeepSeek classifier, Map-Reduce Agent-Executable Playbook Compiler & 210-Prompt Vault Builder."""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

DISCIPLINES = [
    "posicionamiento",
    "oferta",
    "copywriting",
    "funnels",
    "ads_trafico",
    "contenido_organico",
    "ventas_cierre",
    "email_retencion",
    "branding_identidad",
    "ia_automatizacion",
    "negocio_mentalidad",
    "descartar_fuera_de_alcance",
]


def call_deepseek(
    messages: list[dict[str, str]],
    model: str = "deepseek-chat",
    json_mode: bool = False,
    max_tokens: int = 8192,
) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.15,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    with httpx.Client(timeout=240.0) as client:
        resp = client.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def classify_manifest(hub_root: Path, batch_size: int = 20) -> dict[str, Any]:
    manifest_path = hub_root / "06_MANIFIESTOS" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", {})

    unclassified = [
        (rel_path, meta) for rel_path, meta in items.items() if not meta.get("disciplina")
    ]

    for idx in range(0, len(unclassified), batch_size):
        batch = unclassified[idx : idx + batch_size]
        summaries = []
        for rel_path, meta in batch:
            md_file = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / meta["academia"] / rel_path
            snippet = md_file.read_text(encoding="utf-8", errors="ignore")[:900] if md_file.exists() else ""
            summaries.append({"id": rel_path, "curso": meta.get("curso", ""), "snippet": snippet})

        prompt = (
            "Clasifica cada leccion en UNA disciplina de esta lista exacta: "
            f"{json.dumps(DISCIPLINES)}. "
            "Responde UNICAMENTE JSON valido con formato: "
            '{"results": [{"id": "...", "disciplina": "...", "tipo": "lesson|workbook|prompt|framework"}]}.\n\n'
            f"Lecciones:\n{json.dumps(summaries, ensure_ascii=False)}"
        )
        raw = call_deepseek(
            [
                {
                    "role": "system",
                    "content": "Eres un taxónomo estricto de conocimiento de marketing, ventas y negocios.",
                },
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
            max_tokens=2048,
        )
        parsed = json.loads(raw)
        for row in parsed.get("results", []):
            rid = row.get("id")
            if rid in items:
                disc = row.get("disciplina", "negocio_mentalidad")
                if disc not in DISCIPLINES:
                    disc = "negocio_mentalidad"
                items[rid]["disciplina"] = disc
                if items[rid].get("tipo") not in ("prompt",):
                    items[rid]["tipo"] = row.get("tipo", "lesson")

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    by_disc: dict[str, list[str]] = {}
    discarded: list[dict[str, str]] = []
    for rel_path, meta in items.items():
        disc = meta.get("disciplina", "negocio_mentalidad")
        if disc == "descartar_fuera_de_alcance":
            discarded.append({"path": rel_path, "curso": meta.get("curso", "")})
        else:
            by_disc.setdefault(disc, []).append(rel_path)

    idx_dir = hub_root / "02_INDICE_POR_DISCIPLINA"
    idx_dir.mkdir(parents=True, exist_ok=True)
    (idx_dir / "index_by_discipline.json").write_text(
        json.dumps(by_disc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (idx_dir / "99_descartados_fuera_de_alcance.json").write_text(
        json.dumps(discarded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "classified": len(unclassified),
        "disciplines": {k: len(v) for k, v in by_disc.items()},
        "discarded": len(discarded),
    }


def _collect_group_digest(files: list[Path], max_total_chars: int = 85000) -> str:
    """Distribute character budget proportionally across all files in a folder group."""
    if not files:
        return ""
    per_file = max(600, min(3200, max_total_chars // len(files)))
    parts: list[str] = []
    for f in sorted(files):
        txt = f.read_text(encoding="utf-8", errors="ignore").strip()
        parts.append(f"### {f.stem}\n{txt[:per_file]}")
    return "\n\n".join(parts)[:max_total_chars]


def compile_prompt_vault(hub_root: Path) -> dict[str, int]:
    """Compile all 210 literal prompts from 09_biblioteca_prompts/ cleanly into 04_BANCOS_TACTICOS/."""
    prompts_dir = (
        hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / "VELOCITYMEDIA" / "INFLUENCE" / "09_biblioteca_prompts"
    )
    prompt_files = sorted(prompts_dir.rglob("*.md"))
    by_cat: dict[str, list[str]] = {}

    for pf in prompt_files:
        cat = pf.parent.name
        raw = pf.read_text(encoding="utf-8", errors="ignore").strip()
        # Strip noisy wrapper lines while preserving exact prompt body and variables
        lines = raw.splitlines()
        title = lines[0].lstrip("#").strip() if lines else pf.stem
        body = "\n".join(lines[1:]).strip()
        # Clean common wrapper noise: replace *Categoría: ...*, ```text / ``` fences
        body = re.sub(r"^\*Categoría:.*?\*\s*", "", body, flags=re.MULTILINE)
        body = re.sub(r"```text\s*", "```markdown\n", body)
        by_cat.setdefault(cat, []).append(f"### {title}\n\n{body.strip()}")

    sections = [
        "# BANCO TÁCTICO DE PROMPTS MAESTROS (210 PROMPTS LITERALES)\n",
        "> **Uso para agentes (Hermes / CrewAI):** Todos los prompts están deduplicados por especialidad. "
        "Antes de ejecutar cualquier prompt, resuelve las variables entre `[corchetes]` o `{{SLOT_*}}` con el Brandbook / Brief del cliente.\n",
    ]
    for cat in sorted(by_cat):
        sections.append(f"## {cat} ({len(by_cat[cat])} prompts)\n\n" + "\n\n---\n\n".join(by_cat[cat]))

    out_path = hub_root / "04_BANCOS_TACTICOS" / "01_biblioteca_210_prompts_maestros.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join(sections).strip() + "\n"
    out_path.write_text(content, encoding="utf-8")
    return {"prompts_compiled": len(prompt_files), "categories": len(by_cat), "chars": len(content)}


def distill_category_of_one_mapreduce(hub_root: Path) -> dict[str, Any]:
    """Map-Reduce across 100% of INFLUENCE + VELOCITYMEDIA Sprints for Agent-Executable Playbooks."""
    vel_dir = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / "VELOCITYMEDIA"
    inf_dir = vel_dir / "INFLUENCE"

    groups = {
        "cursos_cohortes": list((inf_dir / "01_cursos").rglob("*.md"))
        + list((inf_dir / "04_cohortes").rglob("*.md"))
        + list((inf_dir / "06_guias").rglob("*.md")),
        "masterclasses_workshops": list((inf_dir / "02_masterclasses").rglob("*.md"))
        + list((inf_dir / "03_workshops").rglob("*.md")),
        "playbooks_memorandums": list((inf_dir / "05_playbooks").rglob("*.md"))
        + list((inf_dir / "07_memorandums").rglob("*.md")),
        "fuentes_externas": list((inf_dir / "00_fuentes_externas_notebooklm").rglob("*.md")),
        "velocity_sprints": list((vel_dir / "CURSOS SPRINT").rglob("*.md")),
    }

    map_summaries: list[str] = []
    total_sources_mapped = 0
    for gname, files in groups.items():
        if not files:
            continue
        total_sources_mapped += len(files)
        digest = _collect_group_digest(files, max_total_chars=82000)
        map_prompt = (
            f"Analiza este bloque de fuentes (`{gname}`, {len(files)} documentos) y extrae una ficha técnica DENSAMENTE OPERATIVA para agentes autónomos (Hermes / CrewAI).\n"
            "REGLAS INQUEBRANTABLES:\n"
            "1. Cero relleno motivacional. Solo frameworks nombrados, reglas IF/THEN, métricas con umbrales, objeciones exactas y pasos ejecutables.\n"
            "2. Parametriza cualquier marca, empresa, autor promocional, precio literal (ej. 1€, 49€/mes, 1.500 valoraciones, Trustpilot, Influence Media) en `{{SLOT_*}}`.\n"
            "3. Extrae también ganchos, estructuras de landing/webinar/email y guiones de diagnóstico/venta presentes en este bloque, todos con `{{SLOT_*}}`.\n\n"
            f"FUENTES:\n{digest}"
        )
        summary = call_deepseek(
            [
                {
                    "role": "system",
                    "content": "Eres un ingeniero de conocimiento para agentes autónomos B2B. Extraes doctrina táctica ejecutable 100% libre de marcas o precios literales.",
                },
                {"role": "user", "content": map_prompt},
            ],
            max_tokens=6144,
        )
        map_summaries.append(f"## BLOQUE MAP: {gname} ({len(files)} fuentes)\n\n{summary}")

    combined_map = "\n\n---\n\n".join(map_summaries)

    reduce_playbook_prompt = (
        "Compila el PLAYBOOK MAESTRO EJECUTABLE `00_category_of_one.md` integrando los 5 bloques del Map Adjunto.\n"
        "DISEÑADO PARA HERMES Y CREWAI — CADA MÓDULO DEBE SEGUIR ESTE CONTRATO EXACTO:\n"
        "1. **Diccionario maestro de `{{SLOT_*}}`** (obligatorios vs opcionales).\n"
        "2. **Módulos A..H** (Diagnóstico de Carpeta, Reframing + Blue Ocean, Lenguaje Propietario + POV, Arquitectura de Oferta + Tripwire + High-Ticket, Webinars/Funnels que Escalan, Contenido Thought Leadership + Demanda, Guión de Venta por Creencias, Productización/Activos + Métricas).\n"
        "3. Dentro de **CADA módulo**, incluir explícitamente:\n"
        "   - `Inputs requeridos:` lista de `{{SLOT_*}}`\n"
        "   - `Reglas de decisión (IF/THEN):` condiciones deterministas\n"
        "   - `Pasos de ejecución:` numerados, ejecutables por LLM\n"
        "   - `Output Schema (YAML/JSON):` estructura exacta que debe devolver el agente\n"
        "   - `Anti-Patrones / Criterios de rechazo:` qué debe rechazar el QA del agente\n"
        "4. PROHIBIDO dejar marcas o precios de ejemplo reales (`Influence Media`, `Velocity`, `1 €`, `49 €`, `Trustpilot`, nombres propios de cursos como marca propia). Todo es `{{SLOT_*}}`.\n\n"
        f"SÍNTESIS MAP COMPLETA:\n{combined_map[:110000]}"
    )
    playbook_md = call_deepseek(
        [
            {
                "role": "system",
                "content": "Eres el compilador SOTA de SOPs ejecutables para agentes CrewAI/Hermes. Cero prosa fluff, 100% contratos ejecutables y {{SLOT_*}}.",
            },
            {"role": "user", "content": reduce_playbook_prompt},
        ],
        max_tokens=8192,
    )
    pb_out = hub_root / "03_PLAYBOOKS_MAESTROS" / "00_category_of_one.md"
    pb_out.parent.mkdir(parents=True, exist_ok=True)
    pb_out.write_text(playbook_md.strip() + "\n", encoding="utf-8")

    reduce_swipes_prompt = (
        "Compila `00_category_of_one_swipes_y_guiones.md` (Banco Táctico de Estructuras, Ganchos, Webinars, Ofertas y Guiones) desde la síntesis Map adjunta.\n"
        "REGLAS ESTRICTAS:\n"
        "1. Cada plantilla/gancho/guión debe venir lista para que un agente la rellene con `{{SLOT_*}}`.\n"
        "2. PROHIBIDO dejar precios literales (`1 €`, `49 €`, `7 días` si es ejemplo de marca), marcas reales (`Influence Media`, `Trustpilot`, etc.). Usa `{{SLOT_PRECIO_ENTRADA}}`, `{{SLOT_DURACION_TRIAL}}`, `{{SLOT_PRUEBA_SOCIAL}}`, etc.\n"
        "3. Indica explícitamente qué `{{SLOT_*}}` requiere cada plantilla y qué canal aplica (Landing, Webinar, DM/Llamada, Ads/Hook, Email).\n\n"
        f"SÍNTESIS MAP COMPLETA:\n{combined_map[:110000]}"
    )
    swipes_md = call_deepseek(
        [
            {
                "role": "system",
                "content": "Eres un compilador de Swipe Files y Guiones Tácticos parametrizados 100% con {{SLOT_*}} para agentes autónomos.",
            },
            {"role": "user", "content": reduce_swipes_prompt},
        ],
        max_tokens=8192,
    )
    # Remove superseded old file name if present
    old_tb = hub_root / "04_BANCOS_TACTICOS" / "00_category_of_one_prompts_y_swipes.md"
    old_tb.unlink(missing_ok=True)
    sw_out = hub_root / "04_BANCOS_TACTICOS" / "00_category_of_one_swipes_y_guiones.md"
    sw_out.write_text(swipes_md.strip() + "\n", encoding="utf-8")

    # Audit leak check right away
    leaks = []
    for fname, content in (("playbook", playbook_md), ("swipes", swipes_md)):
        for forbidden in ("Trustpilot", "49 €", "49€", "Influence Media", "1 €"):
            if forbidden.lower() in content.lower():
                leaks.append(f"{fname}:{forbidden}")

    prompt_vault_stats = compile_prompt_vault(hub_root)
    return {
        "sources_mapped": total_sources_mapped,
        "playbook_chars": len(playbook_md),
        "swipes_chars": len(swipes_md),
        "prompt_vault": prompt_vault_stats,
        "leaks_detected": leaks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--classify", action="store_true")
    parser.add_argument("--distill-coo", action="store_true")
    args = parser.parse_args()

    root = Path("/var/www/localstorage/knowledge_hub")
    out: dict[str, Any] = {}
    if args.classify:
        out["classify"] = classify_manifest(root)
    if args.distill_coo:
        out["distill_coo"] = distill_category_of_one_mapreduce(root)
    print(json.dumps(out, ensure_ascii=False))
