# Scripts/Explainer_Report/question_assets.py
import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# ---------- Config ----------
QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"
SUPABASE_BASE_DIR = "The_Big_Question/Explainer_Report/Ai_Responses/Question_Assets"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]

def safe_escape_braces(value: str) -> str:
    # Protect any accidental braces in user-provided values before .format()
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_questions(path: str) -> List[str]:
    raw = load_text(path)
    lines = [ln.strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln]  # drop blank lines

def format_question(q_template: str, ctx: Dict[str, Any]) -> str:
    """
    1) Substitute {condition} (and any other vars) inside the question line itself.
    2) Return the concrete question string to inject into the main prompt as {question}.
    """
    # Escape braces in variable values first
    safe_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    try:
        return q_template.format(**safe_ctx)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Question contained placeholder {{{missing}}} not provided in payload") from e

def build_prompt(template: str, question: str, ctx: Dict[str, Any]) -> str:
    """
    Map all patient/context vars + the fully-substituted question into the prompt template.
    """
    mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    mapping["question"] = safe_escape_braces(question)
    try:
        return template.format(**mapping)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Prompt template missing value for {{{missing}}}") from e

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE) -> str:
    client = OpenAI()
    max_tries = 6
    base_sleep = 1.0

    for attempt in range(1, max_tries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content.strip()
            return text
        except Exception as e:
            # Respect simple rate-limit backoff
            if attempt == max_tries:
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.25 * (attempt - 1))
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

def supabase_write(path: str, content: str):
    # Wrap your existing writer with logging
    write_supabase_file(path, content)

def write_json(path: str, obj: Dict[str, Any]):
    supabase_write(path, json.dumps(obj, ensure_ascii=False, indent=2))

# ---------- Checkpoint & Manifest (stored in Supabase) ----------
def supabase_paths(run_id: str) -> Dict[str, str]:
    base = f"{SUPABASE_BASE_DIR}/{run_id}"
    return {
        "base": base,
        "manifest": f"{base}/manifest.json",
        "checkpoint": f"{base}/checkpoint.json",
    }

def load_supabase_json(path: str) -> Dict[str, Any]:
    """
    Optional: If you later want to *read* manifest/checkpoint from Supabase,
    you already have Engine/Files/read_supabase_file.py. Keeping write-only for now.
    """
    return {}

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

# ---------- Core worker ----------
def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
    """
    Heavy worker that runs in a background thread.
    """
    try:
        logger.info(f"🚀 [Explainer.Run] start run_id={run_id}")

        # Variables from Zapier/Typeform
        ctx = {
            "condition": payload.get("condition", ""),
            "age": payload.get("age", ""),
            "gender": payload.get("gender", ""),
            "ethnicity": payload.get("ethnicity", ""),
            "region": payload.get("region", ""),
            "todays_date": payload.get("todays_date", ""),
        }

        # read files from repo
        prompt_template = load_text(PROMPT_PATH)
        q_templates = load_questions(QUESTIONS_PATH)
        total = len(q_templates)

        paths = supabase_paths(run_id)

        # Create initial manifest & checkpoint
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

        # Persist initial metadata
        write_json(paths["manifest"], manifest)
        write_json(paths["checkpoint"], ckpt)

        # sequential loop; only advance after successful write
        for idx, q_tmpl in enumerate(q_templates):
            # Skip completed (if you later add resume logic by reading manifest/ckpt)
            if idx <= ckpt["last_completed_index"]:
                continue

            # 1) fill {condition} inside the question itself (and any other placeholders)
            filled_q = format_question(q_tmpl, ctx)

            # 2) build full prompt with {question} + patient context
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
            write_json(paths["manifest"], manifest)

            try:
                t0 = time.time()
                ai_text = call_openai(prompt, model=payload.get("model", DEFAULT_MODEL), temperature=TEMPERATURE)
                elapsed = round(time.time() - t0, 3)

                # optional: write a header wrapper around the AI text so each file is self-describing
                header = (
                    f"Run ID: {run_id}\n"
                    f"Index: {idx}\n"
                    f"Question: {filled_q}\n"
                    f"Model: {payload.get('model', DEFAULT_MODEL)}\n"
                    f"Generated at: {now_iso()}\n"
                    f"Latency (s): {elapsed}\n"
                    f"{'-'*80}\n\n"
                )
                supabase_write(outfile, header + ai_text)

                # mark done
                item.update({"status": "done", "completed_at": now_iso()})
                upsert_manifest_item(manifest, item)
                write_json(paths["manifest"], manifest)

                # checkpoint after *successful write*
                ckpt = update_checkpoint(ckpt, idx)
                write_json(paths["checkpoint"], ckpt)

                # small politeness delay (tune/remove if needed)
                time.sleep(0.25)

            except Exception as e:
                item.update({
                    "status": "failed",
                    "failed_at": now_iso(),
                    "error": {"type": type(e).__name__, "message": str(e)},
                })
                upsert_manifest_item(manifest, item)
                write_json(paths["manifest"], manifest)
                # continue to next question

        logger.info(f"✅ [Explainer.Run] completed run_id={run_id} total={total} done="
                    f"{sum(1 for x in manifest['items'] if x['status']=='done')} "
                    f"failed={sum(1 for x in manifest['items'] if x['status']=='failed')}")

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# ---------- Public entrypoint (non-blocking) ----------
def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    This is called by main.py. It *returns immediately* so Zapier isn't held open.
    """
    run_id = data.get("run_id") or f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    data["run_id"] = run_id

    # log inputs
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

    # spin off a background thread — return immediately to Zapier
    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    # Minimal status to caller
    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/"
    }
