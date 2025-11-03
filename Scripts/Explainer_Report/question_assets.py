# Scripts/Explainer_Report/question_assets.py
# GPT-5-mini + OpenAI Responses API + web_search
# Batch Pattern A: One API call returns N answers at once (default N=5), with continuity via a compact registry.
# Writes each item as its own .txt file to Supabase. No batching of *runs*, only batching within a run.
# Requires: openai>=2.6 with Responses API and web_search (your logs show openai==2.6.1 works after removing `response_format` & `temperature`).

import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List

from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =========================
# Config
# =========================

QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"
SUPABASE_BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
# NOTE: gpt-5-mini with Responses API rejects `temperature`; do not send it.
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5"))         # number of questions per API call (pattern A)
MANIFEST_FLUSH_EVERY = int(os.getenv("MANIFEST_FLUSH_EVERY", "5"))

# Continuity registry (compact)
EXPLAINER_MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "5"))
EXPLAINER_MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "3500"))

# Optional parallelism for file writes (I/O) — safe since we still do NOT batch prompts
WRITE_WORKERS = int(os.getenv("SUPABASE_WRITE_WORKERS", "2"))

# =========================
# Singletons
# =========================

CLIENT = OpenAI()                         # Reuse one client to avoid TLS setup overhead
WRITE_POOL = ThreadPoolExecutor(max_workers=WRITE_WORKERS)

# =========================
# Helpers
# =========================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]

def safe_escape_braces(value: str) -> str:
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_questions(path: str) -> List[str]:
    raw = load_text(path)
    lines = [ln.strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln]

def chunked(seq: List[Any], size: int) -> List[List[Any]]:
    return [seq[i:i+size] for i in range(0, len(seq), size)]

def supabase_write_txt(path: str, content: str):
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    supabase_write_txt(path, json.dumps(obj, ensure_ascii=False, indent=2))

def build_registry_block(history_jsons: List[str],
                         max_stats: int = 50,
                         max_insights: int = 50,
                         max_urls: int = 80,
                         max_heads: int = 5) -> str:
    """
    Build a compact registry of previously used values to enforce uniqueness across batches.
    """
    stats, insights, urls, heads = [], [], [], []
    seen_s, seen_i, seen_u = set(), set(), set()

    for h in history_jsons[-EXPLAINER_MAX_QA_IN_CONTEXT:]:
        try:
            obj = json.loads(h)
        except Exception:
            continue
        s = (obj.get("Statistic") or "").strip()
        if s and s not in seen_s:
            stats.append(s); seen_s.add(s)
        ins = (obj.get("Phrase", "") or obj.get("Insight", "")).strip()
        if ins and ins not in seen_i:
            insights.append(ins); seen_i.add(ins)
        ra = obj.get("Related Article") or {}
        u = (ra.get("Related Article", {}) if isinstance(ra, str) else ra.get("Related Article URL", "")).strip()
        # Some models may return different key name; try both
        if not u and isinstance(ra, dict):
            u = (ra.get("Related Article URL") or ra.get("URL") or "").strip()
        if u and u not in seen_u:
            urls.append(u); seen_u.add(u)
        hd = (obj.get("Header") or "").strip()
        if hd:
            heads.append(hd)

    # Trim lengths
    stats = stats[:max_stats]
    insights = insights[:max_insights]
    urls = urls[:max_urls]
    heads = heads[-min(len(heads), max_heads):]

    # Build compact lines
    def join_list(vals, sep=" || "):
        s = sep.join(vals)
        if len(s) > EXPLAINER_MAX_CONTEXT_LENGTH_PER_FIELD():
            return s[:EXPLAINER_MAX_CONTEXT_LENGTH_PER_FIELD()] + "..."
        return s

    registry = (
        "## REGISTRY (DO NOT COPY TO OUTPUT)\n"
        "Use this registry to avoid duplicating values across all *previously written* items.\n"
        f"HEADERS_PREV: {', '.join(heads)}\n"
        f"STATS_USED: {join_list([v for v in stats if v])}\n"
        f"INSIGHTS_USED: {join_list([v for v in insights if v])}\n"
        f"URLS_USED: {join_list([v for v in urls if v])}\n"
    )
    # Ensure total registry block stays within budget
    if len(registry) > EXPLAINER_MAX_CONTEXT_CHARS:
        registry = registry[:EXPLAINER_MAX_CONTEXT_CHARS - 3] + "..."
    return registry

def EXPLAINER_MAX_CONTEXT_LENGTH_PER_FIELD() -> int:
    # Roughly divide among 4 lists, leave headroom for headings
    return max(100, (EXPLAINER_MAX_CONTEXT_CHARS // 6))

def build_batch_prompt(
    base_prompt: str,
    run_id: str,
    batch_index: int,
    ctx: Dict[str, Any],
    batch_items: List[Dict[str, str]],
    registry_block: str
) -> str:
    """
    Build a batch-mode prompt that overrides the single-question OUTPUT FORMAT and asks for:
    {
      "run_id": "...",
      "batch_index": N,
      "items": [ { q_id, Question, Header, Sub-Header, ... }, ... ]
    }
    """
    # Replace single-question slot if present, but keep all guidance above it
    # We do NOT rely on the template's ## OUTPUT FORMAT; we override it.
    # To avoid conflicting instructions, strip any trailing "## OUTPUT FORMAT" section.
    stripped = re.split(r"(?im)^\s*##\s*OUTPUT\s+FORMAT.*$", base_prompt, maxsplit=1)[0]

    profile_block = (
        f"\n\n### BATCH CONTEXT\n"
        f"All questions in this batch share the following PROFILE CONTEXT:\n"
        f"- **Condition**: {ctx.get('condition','')}\n"
        f"- **Age**: {ctx.get('age','')}\n"
        f"- **Gender**: {ctx.get('gender','')}\n"
        f"- **Ethnicity**: {ctx.get('ethnicity','')}\n"
        f"- **Region**: {ctx.get('region','')}\n"
        f"- **Todays Date**: {ctx.get('todays_date','')}\n"
    )

    batch_output_schema = {
        "run_id": "<string - echo the provided run_id>",
        "batch_index": "<integer - 0-based batch index>",
        "items": [
            {
                "q_id": "<echo the q_id from BATCH_INPUT item>",
                "Question": "<verbatim from BATCH_INPUT.question>",
                "Header": "...",
                "Sub-Header": "...",
                "Summary": "Paragraph 1.\\n\\nParagraph 2.\\n\\nParagraph 3.[+ optional 4/5th]",
                "Bullet Points": "Sentence.\\nSentence.\\nSentence.\\nSentence.",
                "Statistic": "...",
                "Insight": "...",
                "Related Article": {
                    "Related Article Title": "...",
                    "Related Article Date": "DD/MM/YYYY",
                    "Related Article Summary": "...",
                    "Related Article Relevance": "...",
                    "Related Article Source": "...",
                    "Related Article URL": "https://..."
                }
            }
        ]
    }

    batch_instructions = f"""
---
## BATCH MODE — OVERRIDE OF SINGLE-QUESTION OUTPUT
You will answer **{len(batch_items)} questions in one call**. **Ignore any single-question “MAIN QUESTION” and “OUTPUT FORMAT” sections above** and instead follow this batch mode:

1) Use the shared PROFILE CONTEXT (see *BATCH CONTEXT* below) for **all** items.
2) You are given `BATCH_INPUT`, an array of objects with `q_id` and `question`.
3) For **each** BATCH_INPUT element, generate **one** item that satisfies the per-item **OUTPUT REQUIREMENTS** defined above (the fields: Question, Header, Sub-Header, Summary, Bullet Points, Statistic, Insight, Related Article).
4) **Uniqueness Guard (very important):**
   - Do **not** repeat any value that appears in `STATS_USED`, `INSIGHTS_USED`, or `URLS_USED` in the *REGISTRY* block below.
   - Within the current batch, ensure **no two items** share the same `"Statistic"` or `"Related Article URL"`. If a collision would occur, choose the next best valid alternative.
   - For each item’s `Related Article`, run at most **2 search queries** and open at most **2 candidate pages**. Prefer {{"NHS","NICE","BMJ","JAMA","NEJM","CDC","WHO","Cochrane"}}. If no suitable article within 6 months is found after 2 queries, pick the **most recent authoritative guideline** (which may be older).
5) **Return exactly one JSON object** in the following format (no extra keys, no commentary):

{json.dumps(batch_output_schema, ensure_ascii=False, indent=2)}

{profile_block}
{registry_block}
### BATCH_INPUT
{json.dumps(batch_items, ensure_ascii=False)}
### END BATCH_INPUT
"""

    return stripped + "\n" + batch_instructions

def parse_batch_response(raw_text: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to salvage if the model added prose before/after JSON
        m = re.search(r"\{[\s\S]*\}\s*$", raw_text.strip())
        if m:
            return json.loads(m.group(0))
        raise

# =========================
# Manifest helpers
# =========================

def supabase_paths(run_id: str) -> Dict[str, str]:
    base = f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs"
    return {
        "base": base,
        "manifest": f"{base}/manifest.json",
        "checkpoint": f"{base}/checkpoint.json",
    }

def init_manifest(run_id: str, total: int, payload_meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "total": total,
        "items": [],
        "payload_meta": payload_meta,
    }

def upsert_manifest_item(manifest: Dict[str, Any], item: Dict[str, Any]) -> None:
    by_id = {x["q_id"]: i for i, x in enumerate(manifest["items"])}
    if item["q_id"] in by_id:
        manifest["items"][by_id[item["q_id"]]] = item
    else:
        manifest["items"].append(item)
    manifest["updated_at"] = now_iso()

def default_checkpoint() -> Dict[str, Any]:
    return {"last_completed_index": -1, "updated_at": now_iso()}

def update_checkpoint(ckpt: Dict[str, Any], idx: int) -> Dict[str, Any]:
    ckpt["last_completed_index"] = idx
    ckpt["updated_at"] = now_iso()
    return ckpt

# =========================
# Main worker
# =========================

def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
    try:
        logger.info(f"🚀 [Explainer.Run] start run_id={run_id}")

        # Shared profile context for the entire run
        ctx = {
            "condition": payload.get("condition", ""),
            "age": payload.get("age", ""),
            "gender": payload.get("gender", ""),
            "ethnicity": payload.get("ethnicity", ""),
            "region": payload.get("region", ""),
            "todays_date": payload.get("todays_date", ""),
        }

        base_prompt = load_text(PROMPT_PATH)
        all_questions = [format_question(q, ctx) for q in load_questions(QUESTIONS_PATH)]
        total = len(all questions := all_questions)
        paths = supabase_paths(run_id)

        manifest = init_manifest(
            run_id,
            total,
            payload_meta={
                "model": DEFAULT_MODEL,
                "ctx": ctx,
                "questions_path": QUESTIONS_PATH,
                "prompt_path": PROMPT_PATH,
                "batch_size": BARNUM := BATCH_SIZE
            },
        )
        ckpt = default_checkpoint()
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        # History store of final per-question JSON strings (for registry)
        history_jsons: List[str] = []

        batches = list(chunked(all_questions, BATCH_SIZE))
        for b_idx, batch in enumerate(batches):
            # Build q_ids for this batch
            batch_enriched = []
            start_index = b_idx * BATCH_SIZE
            for j, q_text in enumerate(batch):
                seq = start_index + j + 1
                qid = f"{seq:02d}_{slugify(q_text)[:50]}_{sha8(q_text)}"
                batch_enriched.append({"q_id": qid, "question": q_text})

            registry_block = build_recap = build_registry_block(history_jsons)

            prompt = build_batch_prompt(
                base_prompt,
                run_id=run_id,
                batch_index=b_idx,
                ctx=ctx,
                batch_items=batch_enriched,
                registry_block=registry_block
            )

            # Call OpenAI once per batch
            t0 = time.time()
            raw = call_openai(prompt, DEFAULT_MODEL)
            elapsed = round(time.time() - t0, 3)

            # Parse batch response
            data = parse_batch_response(raw)
            if not isinstance(data, dict) or "items" not in data or not isinstance(data["items"], list):
                raise ValueError("Model did not return expected batch JSON with 'items' array.")

            items = data["items"]

            # Write each item to its file and update registry/history
            pending_futures = []
            for item in items:
                # Align q_id: if model echoed q_id, trust it; else map by order
                out_qid = item.get("q_id") or batch_enriched[items.index(item)]["q_id"]
                # Backfill Question if missing
                if "Question" not in item or not item["Question"]:
                    item["Question"] = next((bi["question"] for bi in batch_enriched if bi["q_id"] == out_qid), "")

                outfile = f'{paths["base"]}/{out_qid}.txt'
                item_json = json.dumps(item, ensure_ascii=False, indent=2)

                # queue write to overlap with next batch prep
                fut = WRITE_POOL.submit(supabase_write_txt, outfile, item_json)
                pending_futures.append((out_qid, fut))
                history_jsons.append(item_json)

                # Update manifest in memory
                manifest_entry = {
                    "q_id": out_qid,
                    "index": start_index + items.index(item),
                    "question_filled": item.get("Question", ""),
                    "status": "done",
                    "completed_at": now_iso(),
                    "latency_seconds": elapsed  # per-batch; optional to split evenly if desired
                }
                upstart = manifest_entry.copy()
                upsert_manifest_item(manifest, upstart)

            # Flush writes and manifest periodically
            for _, f in pending_futures:
                f.result()

            if ((b_idx + 1) % MANIFEST_FLUSH_RULE := 1) == 0 or (b_idx + 1) == len(batches):
                supabase_write_textjson(paths["manifest"], manifest)

            # Update checkpoint to last question index written
            ckpt = update_checkpoint(ckpt, start_index + len(batch) - 1)
            supabase_write_textjson(paths["checkpoint"], ckpt)

            # tiny courtesy sleep
            time.sleep(0.05)

        logger.info(
            f"✅ [Explainer.Run] completed run_id={run_id} total={total} "
            f"done={len(manifest['items'])} batches={len(batches)}"
        )

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# =========================
# OpenAI call wrapper (Responses API, web_search, no temperature)
# =========================

def call_openai(prompt: str, model: str) -> str:
    """
    Single batch call: returns raw JSON text for the batch.
    - Uses Responses API (no response_format, no temperature for gpt-5-mini)
    - Includes web_search tool
    - Caller is responsible for parsing JSON and writing files
    """
    # Retry only on transient (5xx / timeouts). Bail fast on 4xx.
    max_tries = 6
    backoff = 1.0
    for attempt in range(1, max_tries + 1):
        try:
            resp = CLIENT.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                input=prompt,
            )
            txt = getattr(resp, "nontoken_text", None)  # some SDKs expose this
            if not txt:
                txt = getattr(resp, "output_text", None)
            if not txt and hasattr(resp, "output"):
                # Older 2.x SDKs
                txt = resp.output[0].content[0].text
            if not txt:
                raise ValueError("Empty model response.")
            return txt
        except Exception as e:
            # If it's a 4xx (validation), don't retry
            status = getattr(e, "status_code", None)
            if isinstance(status, int) and 400 <= status < 500:
                raise
            if attempt >= max_tries:
                raise
            logger.warning(f"Transient error on attempt {attempt}: {e} — retrying in {backoff:.1f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 8.0)

# =========================
# Public entrypoint
# =========================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called by main.py. Returns immediately so Zapier isn’t held open.
    """
    run_id = data.get("run_id") or f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    data["run_id"] = run_id

    logger.info("📥 question_assets.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        "condition": data.get("condition"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "ethnicity": data.get("ethnicity"),
        "region": data.get("region"),
        "todays_date": data.get("todays_date"),
        "model": DEFAULT_MODEL,
        "batch_size": BATCH_SIZE
    }, ensure_ascii=False))

    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": f"Explainer report started (GPT-5-mini, batch size={BATCH_SIZE}, Responses+web_search, per-run continuity via compact registry).",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
