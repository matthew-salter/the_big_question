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

DEFAULT_MODEL = "gpt-5-mini"
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "5"))
MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "16000"))

# =========================
# Helpers
# =========================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.strip().lower())
    return s.strip("-")

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]

def safe_escape_braces(value: str) -> str:
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_questions(path: str) -> List[str]:
    return [ln.strip() for ln in load_text(path).splitlines() if ln.strip()]

def format_question(q_template: str, ctx: Dict[str, Any]) -> str:
    safe_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    return q_template.format(**safe_ctx)

def build_prompt(template: str, question: str, ctx: Dict[str, Any], history: List[str]) -> str:
    """
    Append rolling context of previous Q&A JSONs to the system prompt for continuity.
    """
    mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    mapping["question"] = safe_escape_braces(question)

    context_block = ""
    if history:
        joined = "\n\n".join(history[-MAX_QA_IN_CONTEXT:])
        joined = joined[-MAX_CONTEXT_CHARS:]
        context_block = f"\n\n---\n### PRIOR RESPONSES CONTEXT\nThe following are previous question/answer JSONs from this same report run:\n{joined}\n---\n"

    return template.format(**mapping) + context_block

# =========================
# OpenAI call (Responses API + web_search)
# =========================

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE) -> str:
    client = OpenAI()
    max_tries, base_sleep = 6, 1.0

    for attempt in range(1, max_tries + 1):
        try:
            resp = client.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                input=prompt
            )

            text_out = getattr(resp, "output_text", None)
            if not text_out and hasattr(resp, "output") and resp.output:
                text_out = resp.output[0].content[0].text
            if not text_out:
                raise ValueError("Empty response from model")

            obj = json.loads(text_out)
            return json.dumps(obj, ensure_ascii=False, indent=2)

        except Exception as e:
            if attempt == max_tries:
                raise
            delay = base_sleep * (2 ** (attempt - 1)) + 0.25 * (attempt - 1)
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {delay:.2f}s")
            time.sleep(delay)

# =========================
# Supabase helpers
# =========================

def supabase_write_txt(path: str, content: str):
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    supabase_write_txt(path, json.dumps(obj, ensure_ascii=False, indent=2))

def supabase_paths(run_id: str) -> Dict[str, str]:
    base = f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs"
    return {
        "base": base,
        "manifest": f"{base}/manifest.json",
        "checkpoint": f"{base}/checkpoint.json",
    }

# =========================
# Core worker
# =========================

def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
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

        manifest = {
            "run_id": run_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "total": total,
            "items": [],
            "payload_meta": {"model": DEFAULT_MODEL, "temperature": TEMPERATURE, "ctx": ctx},
        }
        ckpt = {"last_completed_index": -1, "updated_at": now_iso()}
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        history = []

        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            filled_q = format_question(q_tmpl, ctx)
            prompt = build_prompt(prompt_template, filled_q, ctx, history)

            q_id = f"{idx+1:02d}_{slugify(filled_q)[:50]}_{sha8(filled_q)}"
            outfile = f'{paths["base"]}/{q_id}.txt'
            item = {"q_id": q_id, "index": idx, "question_filled": filled_q, "status": "started", "started_at": now_iso(), "output_path": outfile}
            manifest["items"].append(item)
            supabase_write_textjson(paths["manifest"], manifest)

            try:
                t0 = time.time()
                ai_json = call_openai(prompt, model=DEFAULT_MODEL, temperature=TEMPERATURE)
                elapsed = round(time.time() - t0, 3)
                supabase_write_txt(outfile, ai_json)
                item.update({"status": "done", "completed_at": now_iso(), "latency_seconds": elapsed})
                supabase_write_textjson(paths["manifest"], manifest)
                ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                supabase_write_textjson(paths["checkpoint"], ckpt)
                history.append(ai_json)
                time.sleep(0.25)
            except Exception as e:
                item.update({"status": "failed", "failed_at": now_iso(), "error": str(e)})
                supabase_write_textjson(paths["manifest"], manifest)

        logger.info(f"✅ [Explainer.Run] completed run_id={run_id} total={total}")

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# =========================
# Entrypoint
# =========================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
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
    }, ensure_ascii=False))

    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
