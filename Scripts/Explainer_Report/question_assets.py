# Scripts/Explainer_Report/question_assets.py

import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =========================
# Config
# =========================

QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"

# IMPORTANT:
# Do NOT include "The_Big_Question" here; write_supabase_file() already
# prepends SUPABASE_ROOT_FOLDER to the path.
SUPABASE_BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"

# Model (env-driven). Recommend OPENAI_MODEL=gpt-5-mini for this stage.
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

# Temperature kept for observability only; NOT passed to Responses API.
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Conversation continuity mode within a run:
# "client" -> rolling transcript included in each request (recommended)
# "none"   -> each batch is stateless
# "server" -> placeholder for future server-side conversation id (falls back to "client")
CONTEXT_MODE = os.getenv("EXPLAINER_CONTEXT_MODE", "client").lower()

# Rolling transcript limits (applies when CONTEXT_MODE != "none")
# Keep these tight for speed.
MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "3"))       # last N Q/A pairs
MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "6000"))    # hard cap to avoid token bloat

# Batching
BATCH_SIZE = max(1, int(os.getenv("BATCH_SIZE", "5")))  # default 5 (12 calls for 60 questions)
POLITENESS_DELAY = float(os.getenv("EXPLAINER_POLITENESS_DELAY", "0.05"))    # small delay between batches

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
    # Protect accidental braces in user-provided values before .format()
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
    Substitute {condition} (and any other vars) inside the question line itself.
    """
    safe_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    try:
        return q_template.format(**safe_ctx)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Question contained placeholder {{{missing}}} not provided in payload") from e

def build_prompt(template: str, question: str, ctx: Dict[str, Any]) -> str:
    """
    Map patient/context vars + the fully-substituted question into the prompt template.
    """
    mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    mapping["question"] = safe_escape_braces(question)
    try:
        return template.format(**mapping)
    except KeyError as e:
        missing = str(e).strip("'")
        raise KeyError(f"Prompt template missing value for {{{missing}}}") from e

def clean_ai_output(ai_text: str) -> str:
    """
    Remove markdown code fences if present and pretty-print JSON if valid.
    Returns a JSON string (pretty-printed) if parseable; otherwise the cleaned raw text.
    """
    cleaned = ai_text.strip()
    # Strip ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # Try JSON parse -> pretty print
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return cleaned

def supabase_write_txt(path: str, content: str):
    """
    Write text content (JSON string inside, but saved as .txt).
    """
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    """
    Convenience for writing JSON objects as text/plain.
    """
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

def update_checkpoint_to_index(ckpt: Dict[str, Any], idx: int) -> Dict[str, Any]:
    ckpt["last_completed_index"] = idx
    ckpt["updated_at"] = now_iso()
    return ckpt

# =========================
# Conversation state (client-side rolling transcript)
# =========================

class ConversationState:
    """
    Maintains a compact rolling Q/A transcript per run for continuity.
    Serialized into the manifest on each step so you can audit/debug.
    """

    def __init__(self):
        self.qa: List[Dict[str, str]] = []  # [{q: "...", a: "..."}]
        self.server_conversation_id: Optional[str] = None  # reserved for future

    def as_text_block(self) -> str:
        """
        Format last N Q/A into a human readable block with strict caps.
        """
        if not self.qa:
            return ""
        subset = self.qa[-MAX_QA_IN_CONTEXT:]
        lines: List[str] = []
        for i, qa in enumerate(subset, 1):
            q = (qa.get("q") or "").strip()
            a = (qa.get("a") or "").strip()
            lines.append(f"Q{i}: {q}\nA{i}: {a}")
        block = "\n\n".join(lines)
        if len(block) > MAX_CONTEXT_CHARS:
            block = block[-MAX_CONTEXT_CHARS:]
        return block

    def push(self, question: str, answer: str) -> None:
        self.qa.append({"q": question, "a": answer})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qa": self.qa[-MAX_QA_IN_CONTEXT:],  # bounded tail only
            "server_conversation_id": self.server_conversation_id,
        }

# =========================
# OpenAI (Responses API)
# =========================

_client = OpenAI()

def call_openai_responses(
    prompt: str,
    model: str = DEFAULT_MODEL,
    *,
    conversation_block: Optional[str] = None,
    server_conversation_id: Optional[str] = None,
) -> str:
    """
    Call OpenAI Responses API with GPT-5 / gpt-5-mini.
    NOTE: Do NOT pass 'temperature' / 'verbosity' / 'reasoning_effort'.
    """
    max_tries = 6
    base_sleep = 1.0

    # Compose final input
    if conversation_block:
        preamble = (
            "You are answering a series of related questions for the same patient/context.\n"
            "Use the prior Q&A for consistency. Avoid re-explaining shared setup unless asked.\n\n"
            "=== Prior Q&A (most recent last) ===\n"
            f"{conversation_block}\n"
            "=== End prior Q&A ===\n\n"
        )
        final_input = f"{preamble}{prompt}"
    else:
        final_input = prompt

    for attempt in range(1, max_tries + 1):
        try:
            kwargs = dict(model=model, input=final_input)
            # If/when the SDK exposes server-side conversation ids:
            # if server_conversation_id:
            #     kwargs["conversation_id"] = server_conversation_id

            resp = _client.responses.create(**kwargs)
            return resp.output_text.strip()

        except Exception as e:
            if attempt == max_tries:
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.25 * (attempt - 1))
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

# =========================
# Batching helpers
# =========================

def build_batch_prompt(
    prompt_template: str,
    batch_questions_filled: List[str],
    ctx: Dict[str, Any],
    conversation_block: str,
) -> str:
    """
    Build a single prompt for a batch of N questions.
    We *embed* the single-question template output for each question,
    and instruct the model to return a JSON array (no extra prose).
    """
    header = ""
    if conversation_block:
        header = (
            "You are continuing the same case. Use the prior Q&A for consistency.\n\n"
            "=== Prior Q&A (most recent last) ===\n"
            f"{conversation_block}\n"
            "=== End prior Q&A ===\n\n"
        )

    # For each filled question, we still include the same per-question structure
    # by applying the single-question template (done before this function),
    # so the model sees identical framing per item.
    numbered = []
    for i, filled_question in enumerate(batch_questions_filled, 1):
        # Build the *final* per-item prompt by injecting the per-question text
        per_item_prompt = prompt_template.format(
            condition=safe_escape_braces(ctx.get("condition", "")),
            age=safe_escape_braces(ctx.get("age", "")),
            gender=safe_escape_braces(ctx.get("gender", "")),
            ethnicity=safe_escape_braces(ctx.get("ethnicity", "")),
            region=safe_escape_braces(ctx.get("region", "")),
            todays_date=safe_escape_braces(ctx.get("todays_date", "")),
            question=safe_escape_braces(filled_question),
        )
        numbered.append(f"{i}. {per_item_prompt}")

    instructions = (
        "Return answers as a JSON array, where each item has exactly:\n"
        '{ "index": <1-based integer matching the numbering>,\n'
        '  "question_filled": "<the exact question string>",\n'
        '  "answer_json_text": "<the answer as valid JSON or clean plain text>" }\n'
        "Do not include any extra text before or after the JSON array."
    )

    return f"{header}Answer the following {len(batch_questions_filled)} questions.\n\n" + \
           "\n\n".join(numbered) + "\n\n" + instructions

def parse_batch_response(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse the model's batched JSON array and return list of items.
    Raises ValueError if parsing fails.
    """
    cleaned = clean_ai_output(raw_text)
    try:
        arr = json.loads(cleaned)
        if not isinstance(arr, list):
            raise ValueError("Model did not return a JSON array.")
        return arr
    except Exception as e:
        # Attach a short preview to help diagnose
        preview = cleaned[:600]
        raise ValueError(f"Batch parse failed: {e}\nPreview:\n{preview}")

# =========================
# Core worker (background)
# =========================

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

        # Load template & questions from the repo
        prompt_template = load_text(PROMPT_PATH)
        q_templates = load_questions(QUESTIONS_PATH)
        total = len(q_templates)

        paths = supabase_paths(run_id)

        # Initialize manifest & checkpoint
        manifest = init_manifest(
            run_id,
            total,
            payload_meta={
                "model": payload.get("model", DEFAULT_MODEL),
                "temperature": TEMPERATURE,  # observed only; not sent
                "ctx": ctx,
                "questions_path": QUESTIONS_PATH,
                "prompt_path": PROMPT_PATH,
                "context_mode": CONTEXT_MODE,
                "max_qa_in_context": MAX_QA_IN_CONTEXT,
                "max_context_chars": MAX_CONTEXT_CHARS,
                "batch_size": BATCH_SIZE,
            },
        )
        ckpt = default_checkpoint()

        # Conversation state for this run
        convo = ConversationState()

        # Persist initial metadata (in the same folder as outputs)
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        # BATCHED LOOP
        idx = 0
        while idx < total:
            end = min(idx + BATCH_SIZE, total)

            # Prepare filled questions for this batch
            batch_qs_filled = [format_question(q_templates[j], ctx) for j in range(idx, end)]

            # Pre-register manifest items with status "started"
            for j, q_text in enumerate(batch_qs_filled):
                gidx = idx + j
                q_id = f"{gidx+1:02d}_{slugify(q_text)[:50]}_{sha8(q_text)}"
                item = {
                    "q_id": q_id,
                    "index": gidx,
                    "question_template": q_templates[gidx],
                    "question_filled": q_text,
                    "status": "started",
                    "started_at": now_iso(),
                    "output_path": f'{paths["base"]}/{q_id}.txt',
                    "retries": 0,
                    "error": None,
                }
                upsert_manifest_item(manifest, item)

            # Continuity block (small tail)
            conversation_block = ""
            if CONTEXT_MODE != "none":
                conversation_block = convo.as_text_block()

            # Build single batch prompt
            batch_prompt = build_batch_prompt(
                prompt_template=prompt_template,
                batch_questions_filled=batch_qs_filled,
                ctx=ctx,
                conversation_block=conversation_block,
            )

            # Call model once for this batch
            t0 = time.time()
            raw = call_openai_responses(
                batch_prompt,
                model=payload.get("model", DEFAULT_MODEL),
                conversation_block=None,           # we already embedded continuity in the prompt
                server_conversation_id=None,       # reserved; not used
            )
            elapsed = round(time.time() - t0, 3)

            # Parse and write each item
            try:
                arr = parse_batch_response(raw)
            except Exception as e:
                # Mark entire batch as failed with one shared error; proceed to next batch
                err_msg = {"type": type(e).__name__, "message": str(e)}
                for j, q_text in enumerate(batch_qs_filled):
                    gidx = idx + j
                    q_id = f"{gidx+1:02d}_{slugify(q_text)[:50]}_{sha8(q_text)}"
                    item = {
                        "q_id": q_id,
                        "index": gidx,
                        "question_template": q_templates[gidx],
                        "question_filled": q_text,
                        "status": "failed",
                        "failed_at": now_iso(),
                        "output_path": f'{paths["base"]}/{q_id}.txt',
                        "retries": 0,
                        "error": err_msg,
                    }
                    upsert_manifest_item(manifest, item)

                manifest["conversation_state"] = convo.to_dict()
                supabase_write_textjson(paths["manifest"], manifest)
                # Checkpoint moves to end-1 only if contiguous done; here none were done in this batch.
                # Keep prior checkpoint unchanged.
                # Move to next batch
                idx = end
                time.sleep(POLITENESS_DELAY)
                continue

            # Write outputs and mark done
            # Keep a small tail of the last few Q/As for continuity
            tail_qa_to_push: List[Dict[str, str]] = []

            for item_obj in arr:
                # Defensive pulls
                try:
                    i1 = int(item_obj.get("index", 0))
                except Exception:
                    i1 = 0
                if i1 < 1 or i1 > len(batch_qs_filled):
                    continue

                gidx = idx + (i1 - 1)
                q_text = batch_qs_filled[i1 - 1]
                q_id = f"{gidx+1:02d}_{slugify(q_text)[:50]}_{sha8(q_text)}"
                outfile = f'{paths["base"]}/{q_id}.txt'

                # Model returns answer_json_text (JSON or text). Clean to strip fences.
                answer_text = (item_obj.get("answer_json_text") or "").strip()
                final_output = clean_ai_output(answer_text)

                # Save as .txt but content is JSON/text
                supabase_write_txt(outfile, final_output)

                # Mark done
                item_rec = {
                    "q_id": q_id,
                    "index": gidx,
                    "question_template": q_templates[gidx],
                    "question_filled": q_text,
                    "status": "done",
                    "completed_at": now_iso(),
                    "latency_seconds": elapsed,   # same elapsed for all items in this batch
                    "output_path": outfile,
                    "retries": 0,
                    "error": None,
                }
                upsert_manifest_item(manifest, item_rec)

                # Prepare tail push (we'll only push a couple to keep context lean)
                tail_qa_to_push.append({"q": q_text, "a": final_output})

            # Update conversation with last 2 from this batch (keeps context lean)
            if CONTEXT_MODE != "none" and tail_qa_to_push:
                for qa in tail_qa_to_push[-2:]:
                    convo.push(qa["q"], qa["a"])

            # Persist manifest + checkpoint + convo
            manifest["conversation_state"] = convo.to_dict()
            ckpt = update_checkpoint_to_index(ckpt, end - 1)
            supabase_write_textjson(paths["manifest"], manifest)
            supabase_write_textjson(paths["checkpoint"], ckpt)

            # Next batch
            idx = end
            if POLITENESS_DELAY > 0:
                time.sleep(POLITENESS_DELAY)

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
        "context_mode": CONTEXT_MODE,
        "batch_size": BATCH_SIZE,
    }, ensure_ascii=False))

    # Spin off background thread — return immediately to Zapier
    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Batched results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
