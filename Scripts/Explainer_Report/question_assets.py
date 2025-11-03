# Scripts/Explainer_Report/question_assets.py
# GPT-5-mini + OpenAI Responses API + web_search
# Batch Pattern A: one API call answers N questions; enforce cross-batch continuity via a compact registry.
# Writes each item as its own .txt to Supabase. No cross-run memory. No "thread_id". No response_format. No temperature.

import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =========================
# Config
# =========================

QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"
SUPABASE_BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # must be 2.x Responses-supported model
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5"))           # N questions per API call
MANIFEST_FLUSH_EVERY = int(os.getenv("MANIFEST_FLUSH_EVERY", "1"))  # flush manifest every N batches

# Continuity registry sizing
EXPLAINER_MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "5"))
EXPLAINER_MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "3500"))

# Async write pool (I/O only; model calls remain sequential)
WRITE_WORKERS = int(os.getenv("SUPABASE_WRITE_WORKERS", "2"))

# =========================
# Singletons
# =========================

CLIENT = OpenAI()  # reuse a single client per process for lower latency
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
    # protect curly braces if you ever interpolate text into a .format template
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_questions(path: str) -> List[str]:
    raw = load_text(path)
    lines = [ln.strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln]

def chunked(seq: List[Any], size: int) -> List[List[Any]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]

def supabase_write_txt(path: str, content: str):
    # run in thread-pool to overlap with next API call
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    supabase_write_txt(path, json.dumps(obj, ensure_ascii=False, indent=2))

# ===== Continuity registry (compact) =====

def build_registry_block(
    prior_item_jsons: List[str],
    max_stats: int = 50,
    max_insights: int = 50,
    max_urls: int = 80,
    max_heads: int = 5,
) -> str:
    """Build a compact registry of previously used values to avoid repeats across batches."""
    # Only look at the last EXPLAINER_MAX_QA_IN_CONTEXT items for concision
    window = prior_item_jsons[-EXPLAINER_MAX_QA_IN_CONTEXT:]

    stats, insights, urls, heads = [], [], [], []
    seen_stats, seen_ins, seen_urls = set(), set(), set()

    for s in reversed(window):  # newest first
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        st = (obj.get("Statistic") or "").strip()
        if st and st not in seen_stats:
            stats.append(st); seen_stats.add(st)
        ins = (obj.get("Insight") or "").strip()
        if ins and ins not in set(stats):  # minimal dedupe
            if ins not in seen_ins:
                insights.append(ins); seen_ins.add(ins)
        ra = obj.get("Related Article") or {}
        if isinstance(ra, dict):
            url = (ra.get("Related Article URL") or ra.get("URL") or "").strip()
            if url and url not in seen_urls:
                urls.append(url); seen_urls.add(url)
        hd = (obj.get("Header") or "").strip()
        if hd:
            heads.append(hd)

    # Bound sizes
    stats = stats[:max_stats]
    insights = insights[:max_ins]
    urls = urls[:max_urls]
    heads = heads[:max_heads]

    def clip_join(values: List[str], cap: int) -> str:
        s = " || ".join(values)
        return (s if len(s) <= cap else s[: max(0, cap - 3)] + "...")

    # split the budget across fields
    per_field_cap = max(200, EXPLAINER_MAX_CONTEXT_CHARS // 4)

    registry = (
        "## REGISTRY (DO NOT COPY TO OUTPUT)\n"
        "Use this registry to avoid repeating values from prior items in this run.\n"
        f"HEADERS_PREV: {' | '.join(heads)}\n"
        f"STATS_USED: {clip_join(stats, per_field_cap)}\n"
        f"INSIGHTS_USED: {clip_join(insights, per_field_cap)}\n"
        f"URLS_USED: {clip_join(urls, per_field_cap)}\n"
    )
    if len(registry) > EXPLAINER_MAX_CHARS():
        registry = registry[: EXPLAINER_MAX_CHARS() - 3] + "..."
    return registry

def EXPLAINER_MAX_CHARS() -> int:
    # Overall hard cap for the registry text
    return max(800, EXPLAINER_MAX_CONTEXT_CHARS)

# ===== Batch prompt builder (Pattern A) =====

def build_batch_prompt(
    base_template: str,
    ctx: Dict[str, Any],
    run_id: str,
    batch_index: int,
    batch_items: List[Dict[str, str]],
    registry_block: str,
) -> str:
    # Strip the single-question OUTPUT FORMAT block to avoid brace conflicts with f-strings/JSON.
    # Keep all guidance above it (INSTRUCTIONS, REPORT DELIVERY STYLE, etc.).
    preamble = re.split(r"(?im)^\s*##\s*OUTPUT\s+FORMAT.*$", base_template, maxsplit=1)[0]

    # Fill profile placeholders only (NOT {question}; we are in batch mode)
    fmt_map = {
        "condition": safe_escape_braces(ctx.get("condition", "")),
        "age": safe_escape_braces(ctx.get("age", "")),
        "gender": safe_escape_braces(ctx.get("gender", "")),
        "ethnicity": safe_escape_braces(ctx.get("ethnicity", "")),
        "region": safe_escape_braces(ctx.get("region", "")),
        "todays_date": safe_escape_braces(ctx.get("todays_date", "")),
        "question": "See BATCH_INPUT below.",  # neutralize single-question slot
    }
    prefilled = preamble.format(**fmt_map)

    # Schema shown to the model (as literal JSON example)
    batch_schema = {
        "run_id": "<string - echo the provided run_id>",
        "batch_index": "<integer - 0-based batch index>",
        "items": [
            {
                "q_id": "<echo the q_id from BATCH_INPUT item>",
                "Question": "<verbatim from BATCH_INPUT.question>",
                "Header": "<= 40 chars>",
                "Sub-Header": "<= 60 chars>",
                "Summary": "Paragraph 1.\\n\\nParagraph 2.\\n\\nParagraph 3.[+ optional 4/5]",
                "Bullet Points": "Sentence.\\nSentence.\\nSentence.\\nSentence.",
                "Statistic": "<percent/ratio/count specific to this Question>",
                "Insight": "<= 200 chars>",
                "Related Article": {
                    "Related Article Title": "<= 40 chars>",
                    "Related Article Date": "DD/MM/YYYY",
                    "Related Article Summary": "<= 300 chars>",
                    "Related Article Relevance": "<= 300 chars>",
                    "Related Article Source": "<publisher/org>",
                    "Related Article URL": "https://..."
                }
            }
        ]
    }

    batch_overrides = f"""
---
## BATCH MODE — OVERRIDE OF SINGLE-QUESTION FORMAT

You will answer **{len(batch_items)} questions in one call**. Ignore any single-question “MAIN QUESTION” and “OUTPUT REQUIREMENTS/OUTPUT FORMAT” above and **use this batch format** instead.

**Per-item requirements** (apply to each item in `items[]`):
- Use the shared PROFILE CONTEXT (from the preamble) for all items in this batch.
- For each BATCH_INPUT `question`, produce exactly one `items[]` element with fields shown in `BATCH_OUTPUT_SCHEMA`.
- `Summary` must be **3–5 short paragraphs**, separated by **exactly `\\n\\n`**, no “Paragraph 1/2” labels.
- `Statistic` must be **specific to the Question** (e.g., an outcome/adherence/prevalence figure).
- `Related Article` must be **from an authoritative source**, prefer {{NHS, NICE, BMJ, JAMA, NEJM, CDC, WHO, Cochrane}}.
  - Use `web_search` tool.
  - Run **≤ 2 search queries** and open **≤ 2 candidate pages** per item.
  - Require `Related Article Date` within **6 months** of `{ctx.get('todays_date','')}`; if none after 2 queries, pick the **most recent guideline** (may be older).
  - Copy the **final loaded** `https://` URL exactly; do **not** return “Unavailable”.

**Uniqueness guard (very important):**
- Do **not** repeat any value in `STATS_USED`, `INSIGHTS_USED`, `URLS_USED` from the REGISTRY below.
- Within this batch, ensure no two items have the same `Statistic` or `Related Article URL`. If a collision would occur, choose a different valid alternative.

**BATCH_OUTPUT_SCHEMA** (return exactly one JSON object with this shape; no extra keys):
{json.dumps(batch_schema, ensure_ascii=False, indent=2)}

### REGISTRY (read-only)
{registry_block}

### BATCH_INPUT
{json.dumps(batch_items, ensure_ascii=False)}
### END BATCH_INPUT
"""
    return prefilled + "\n" + batch_overrides

# =========================
# OpenAI Responses API
# =========================

def call_openai(prompt: str, model: str) -> str:
    """
    One Responses API call. No temperature, no response_format. With web_search tool.
    Retries only on transient errors.
    """
    max_tries = 6
    backoff = 1.0
    for attempt in range(1, max_tries + 1):
        try:
            resp = CLIENT.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                input=prompt,
            )
            txt = getattr(resp, "output_text", None)
            if not txt and hasattr(resp, "output"):
                txt = resp.output[0].content[0].text
            if not txt:
                raise ValueError("Empty model response.")
            return txt
        except Exception as e:
            status = getattr(e, "status_code", None)
            if isinstance(status, int) and 400 <= status < 500:
                # invalid request — don't retry
                raise
            if attempt >= max_tries:
                raise
            logger.warning(f"Transient OpenAI error attempt {attempt}: {e} — retrying in {backoff:.1f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 8.0)

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
# Worker (sequential batches)
# =========================

def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
    try:
        logger.info(f"🚀 [Explainer.Run] start run_id={run_id}")

        # Shared profile context for this run
        ctx = {
            "condition": payload.get("condition", ""),
            "age": payload.get("age", ""),
            "gender": payload.get("gender", ""),
            "ethnicity": payload.get("ethnicity", ""),
            "region": payload.get("region", ""),
            "todays_date": payload.get("todays_date", ""),
        }

        base_template = load_text(PROMPT_PATH)
        # Prepare question list with {placeholders} filled from ctx
        raw_questions = load_text(QUESTIONS_PATH)
        questions = []
        fmt_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
        for line in (ln.strip() for ln in raw_questions.splitlines()):
            if not line:
                continue
            q = line.format(**fmt_ctx)
            questions.append(q)
        total = len(questions)

        paths = supabase_paths(run_id)
        manifest = init_manifest(
            run_id,
            total,
            payload_meta={
                "model": DEFAULT_MODEL,
                "ctx": ctx,
                "questions_path": QUESTIONS_PATH,
                "prompt_path": PROMPT_PATH,
                "batch_size": BATCH_SIZE,
            },
        )
        ckpt = default_checkpoint()
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        history_jsons: List[str] = []  # final per-question JSON strings from prior batches

        batches = chunked(questions, BATCH_SIZE)
        for b_idx, batch in enumerate(batches):
            start_index = b_idx * BATCH_SIZE

            # Build batch input objects with stable q_ids
            batch_items = []
            for j, q_text in enumerate(batch):
                seq = start_index + j + 1
                qid = f"{seq:02d}_{slugify(q_text)[:50]}_{sha8(q_text)}"
                batch_items.append({"q_id": qid, "question": q_text})

            # Build compact registry from recent history
            registry_block = build_registry_block(history_jsons)

            # Compose final prompt (preamble + batch override + BATCH_INPUT + registry)
            prompt = build_batch_prompt(
                base_template=base_template,
                ctx=ctx,
                run_id=run_id,
                batch_index=b_idx,
                batch_items=batch_items,
                registry_block=registry_block,
            )

            # Call OpenAI once for the whole batch
            t0 = time.time()
            raw = call_openai(prompt, DEFAULT_MODEL)
            gen_elapsed = round(time.time() - t0, 3)

            # Parse and validate
            parsed = parse_batch_response(raw)
            items = parsed.get("items", [])
            if not isinstance(items, list) or not items:
                raise ValueError("Model returned no items in batch response.")

            # Write each item as its own file; update registry & manifest
            pending_writes: List[Tuple[str, Any]] = []
            for idx_in_batch, item in enumerate(items):
                qid = item.get("q_id") or batch_items[idx_in_batch]["q_id"]
                item.setdefault("q_id", qid)
                item.setdefault("Question", batch_items[idx_in_batch]["question"])

                out_path = f"{paths['base']}/{qid}.txt"
                item_json = json.dumps(item, ensure_ascii=False, indent=2)
                pending_writes.append((out_path, WRITE_POOL.submit(supabase_write_txt, out_path, item_json)))

                # Update continuity store
                history_jsons.append(item_json)

                # Manifest (index in full run)
                seq_index = start_index + idx_in_batch
                manifest_entry = {
                    "q_id": qid,
                    "index": seq_index,
                    "question_filled": item.get("Question", ""),
                    "status": "done",
                    "completed_at": now_iso(),
                    "latency_seconds": gen_elapsed  # per-batch gen time (shared across items)
                }
                upsert_manifest_item(manifest, manifest_entry)

            # Wait for I/O of this batch
            for path, fut in pending_writes:
                fut.result()
                logger.info(f"✅ Wrote question file: {path}")

            # Flush manifest periodically or at end of run
            if ((b_idx + 1) % MANIFEST_FLUSH_EVERY == 0) or (b_idx + 1 == len(batches)):
                supabase_write_textjson(paths["manifest"], manifest)

            # Advance checkpoint to last question of this batch
            ckpt = update_checkpoint(ckpt, start_index + len(batch) - 1)
            supabase_write_textjson(paths["checkpoint"], ckpt)

            # tiny courtesy pause
            time.sleep(0.05)

        logger.info(f"✅ [Explainer.Run] completed run_id={run_id} total_questions={total} batches={len(batches)}")

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# =========================
# Public entrypoint
# =========================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns immediately so Render/Zapier request thread is free; the real work happens in a daemon thread.
    """
    run_id = data.get("run_id") or f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    data["run_id"] = run_id

    logger.info("📢 Starting question_assets.run_prompt with payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        "condition": data.get("condition"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "ethnicity": data.get("ethnicity"),
        "region": data.get("region"),
        "todays_date": data.get("todays_date"),
        "model": DEFAULT_MODEL,
        "batch_size": BATCH_SIZE,
    }, ensure_ascii=False))

    t = new_thread = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    new_thread.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": f"Explainer report started (GPT-5-mini, batch size={BATCH_SIZE}, Responses+web_search, per-run continuity).",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
