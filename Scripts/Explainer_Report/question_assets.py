# Scripts/Explainer_Report/question_assets.py

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
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =========================
# Config
# =========================

QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"

SUPABASE_BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"

# Use GPT-5-mini with web_search
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

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
    return [ln for ln in lines if ln]  # drop blank lines

def format_question(q_template: str, ctx: Dict[str, Any]) -> str:
    safe_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    try:
        return q_template.format(**safe_ctx)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Question contained placeholder {{{missing}}} not provided in payload") from e

def build_prompt(template: str, question: str, ctx: Dict[str, Any]) -> str:
    mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    mapping["question"] = safe_escape_braces(question)
    try:
        return template.format(**mapping)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Prompt template missing value for {{{missing}}}") from e

# =========================
# OpenAI call (GPT-5-mini + web_search + thread memory)
# =========================

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE,
                thread_id_path: str = None) -> str:
    """
    Call GPT-5-mini with persistent thread memory + web_search.
    The same thread_id is reused so the model 'remembers' earlier outputs.
    """
    client = OpenAI()
    max_tries, base_sleep = 6, 1.0

    # Read or create a thread id
    thread_id = None
    if thread_id_path and os.path.exists(thread_id_path):
        with open(thread_id_path, "r", encoding="utf-8") as f:
            thread_id = f.read().strip()

    for attempt in range(1, max_tries + 1):
        try:
            resp = client.responses.create(
                model=model,
                temperature=temperature,
                tools=[{"type": "web_search"}],
                input=prompt,
                thread_id=thread_id,      # ← memory continuity
            )

            # Save thread_id for reuse
            if thread_id_path:
                tid = getattr(resp, "thread_id", None)
                if tid:
                    with open(thread_id_path, "w", encoding="utf-8") as f:
                        f.write(tid)

            # Extract text output
            text_out = getattr(resp, "output_text", None)
            if not text_out:
                try:
                    text_out = resp.output[0].content[0].text
                except Exception:
                    text_out = ""

            if not text_out:
                raise ValueError("Empty response from OpenAI Responses API")

            # Parse JSON
            obj = json.loads(text_out)
            return json.dumps(obj, ensure_ascii=False, indent=2)

        except Exception as e:
            if attempt == max_tries:
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.25 * (attempt - 1))
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

# =========================
# Output cleaning
# =========================

def clean_ai_output(ai_text: str) -> str:
    cleaned = ai_text.strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return cleaned

def supabase_write_txt(path: str, content: str):
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    supabase_write_txt(path, json.dumps(obj, ensure_ascii=False, indent=2))

# =========================
# Checkpoint & Manifest
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
# Core worker (sequential)
# =========================

def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
    """
    Sequential loop (no batching) with GPT-5-mini + thread continuity.
    """
    try:
        logger.info(f"🚀 [Explainer.Run] start run_id={run_id}")

        ctx = {
            "condition": payload.get("condition", ""),
            "age": payload.get("age", ""),
            "gender": payload.get("gender", ""),
            "ethnicity": payload.get("ethnicity", ""),
            "region": payload.get("region", ""),
            "todays_date": payload.get("todays_date", ""),
        }

        prompt_template = load_text(PROMPT_PATH)
        q_templates = load_questions(QUESTIONS_PATH)
        total = len(q_templates)
        paths = supabase_paths(run_id)

        manifest = init_manifest(
            run_id,
            total,
            payload_meta={
                "model": payload.get("model", DEFAULT_MODEL),
                "temperature": TEMPERATURE,
                "ctx": ctx,
                "questions_path": QUESTIONS_PATH,
                "prompt_path": PROMPT_PATH,
            },
        )
        ckpt = default_checkpoint()

        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        # Thread memory persistence file
        thread_id_path = f"/tmp/{run_id}_threadid.txt"

        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            filled_q = format_question(q_tmpl, ctx)
            prompt = build_prompt(prompt_template, filled_q, ctx)

            q_id = f"{idx+1:02d}_{slugify(filled_q)[:50]}_{sha8(filled_q)}"
            outfile = f'{paths["base"]}/{q_id}.txt'

            item = {
                "q_id": q_id,
                "index": idx,
                "question_template": q_tmpl,
                "question_filled": filled_q,
                "status": "started",
                "started_at": now_iso(),
                "output_path": outfile,
                "retries": 0,
                "error": None,
            }
            upsert_manifest_item(manifest, item)
            supabase_write_textjson(paths["manifest"], manifest)

            try:
                t0 = time.time()
                ai_text = call_openai(
                    prompt,
                    model=payload.get("model", DEFAULT_MODEL),
                    temperature=TEMPERATURE,
                    thread_id_path=thread_id_path
                )
                elapsed = round(time.time() - t0, 3)

                final_output = clean_ai_output(ai_text)
                supabase_write_txt(outfile, final_output)

                item.update({"status": "done", "completed_at": now_iso(), "latency_seconds": elapsed})
                upsert_manifest_item(manifest, item)
                supabase_write_textjson(paths["manifest"], manifest)

                ckpt = update_checkpoint(ckpt, idx)
                supabase_write_textjson(paths["checkpoint"], ckpt)

                # Politeness delay to avoid rate spikes
                time.sleep(0.25)

            except Exception as e:
                item.update({
                    "status": "failed",
                    "failed_at": now_iso(),
                    "error": {"type": type(e).__name__, "message": str(e)},
                })
                upsert_manifest_item(manifest, item)
                supabase_write_textjson(paths["manifest"], manifest)

        logger.info(
            f"✅ [Explainer.Run] completed run_id={run_id} total={total} "
            f"done={sum(1 for x in manifest['items'] if x['status']=='done')} "
            f"failed={sum(1 for x in manifest['items'] if x['status']=='failed')}"
        )

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# =========================
# Public entrypoint (non-blocking)
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
        "model": data.get("model", DEFAULT_MODEL),
    }, ensure_ascii=False))

    # Background thread to avoid Zapier timeout
    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
