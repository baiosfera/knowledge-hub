"""DeepSeek classifier and {{SLOT_*}} Playbook / Tactical Bank distiller."""

import argparse
import json
import os
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
    max_tokens: int = 4096,
) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    with httpx.Client(timeout=180.0) as client:
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
        (rel_path, meta)
        for rel_path, meta in items.items()
        if not meta.get("disciplina")
    ]

    for idx in range(0, len(unclassified), batch_size):
        batch = unclassified[idx : idx + batch_size]
        summaries = []
        for rel_path, meta in batch:
            md_file = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / meta["academia"] / rel_path
            snippet = ""
            if md_file.exists():
                snippet = md_file.read_text(encoding="utf-8", errors="ignore")[:900]
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
                {"role": "system", "content": "Eres un taxónomo estricto de conocimiento de marketing, ventas y negocios."},
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
                items[rid]["tipo"] = row.get("tipo", "lesson")

        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

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
    return {"classified": len(unclassified), "disciplines": {k: len(v) for k, v in by_disc.items()}, "discarded": len(discarded)}


def distill_category_of_one(hub_root: Path) -> dict[str, int]:
    """Distill 00_category_of_one.md ({{SLOT_*}}) and its tactical prompt/swipe bank."""
    influence_dir = hub_root / "01_TRANSCRIPCIONES_LIMPIAS" / "VELOCITYMEDIA" / "INFLUENCE"
    md_files = sorted(influence_dir.glob("*.md"))
    if not md_files:
        raise RuntimeError(f"No .md files found in {influence_dir}")

    # Build bounded digest across all INFLUENCE lessons
    chunks: list[str] = []
    for f in md_files:
        text = f.read_text(encoding="utf-8", errors="ignore").strip()
        chunks.append(f"## SOURCE: {f.stem}\n{text[:2400]}")
    corpus_digest = "\n\n".join(chunks)[:110000]

    playbook_prompt = (
        "A partir de las transcripciones reales de INFLUENCE adjuntas, compila el Playbook Maestro Universal "
        "`00_category_of_one.md`.\n"
        "REGLAS ESTRICTAS:\n"
        "1. 100% agnóstico a marca: reemplaza cualquier marca, precio o persona real por variables algebraicas "
        "`{{SLOT_MARCA}}`, `{{SLOT_NICHO}}`, `{{SLOT_AVATAR}}`, `{{SLOT_MECANISMO_UNICO}}`, `{{SLOT_PRECIO_HIGH_TICKET}}`, etc.\n"
        "2. Estructura accionable con frameworks exactos, reglas de decisión, métricas y pasos reproducibles por agentes.\n"
        "3. Cero relleno motivacional; solo doctrina táctica fiel a las fuentes.\n\n"
        f"FUENTES:\n{corpus_digest}"
    )
    playbook_md = call_deepseek(
        [
            {"role": "system", "content": "Eres el compilador SOTA de Playbooks Universales {{SLOT_*}} para agentes de marketing y ventas."},
            {"role": "user", "content": playbook_prompt},
        ],
        max_tokens=8192,
    )
    pb_out = hub_root / "03_PLAYBOOKS_MAESTROS" / "00_category_of_one.md"
    pb_out.parent.mkdir(parents=True, exist_ok=True)
    pb_out.write_text(playbook_md.strip() + "\n", encoding="utf-8")

    tactical_prompt = (
        "Extrae del corpus INFLUENCE adjunto un Banco Táctico deduplicado con:\n"
        "1. Prompts literales y estructuras de prompts para IA.\n"
        "2. Estructuras de swipe files, ganchos, ofertas y guiones de diagnóstico/venta.\n"
        "3. Checklists operativos paso a paso.\n"
        "Usa variables `{{SLOT_*}}` donde aplique y NO inventes ejemplos fuera de las fuentes.\n\n"
        f"FUENTES:\n{corpus_digest}"
    )
    tactical_md = call_deepseek(
        [
            {"role": "system", "content": "Eres un extractor de bancos tácticos (prompts, swipe files, guiones y checklists)."},
            {"role": "user", "content": tactical_prompt},
        ],
        max_tokens=8192,
    )
    tb_out = hub_root / "04_BANCOS_TACTICOS" / "00_category_of_one_prompts_y_swipes.md"
    tb_out.parent.mkdir(parents=True, exist_ok=True)
    tb_out.write_text(tactical_md.strip() + "\n", encoding="utf-8")

    return {"playbook_chars": len(playbook_md), "tactical_chars": len(tactical_md), "sources_used": len(md_files)}


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
        out["distill_coo"] = distill_category_of_one(root)
    print(json.dumps(out, ensure_ascii=False))
