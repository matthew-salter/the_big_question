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

# Models & generation controls
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # or "gpt-5"
# Keep env for observability only; not passed to Responses API due to model restrictions.
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Conversation continuity mode within a run:
# "client" -> rolling transcript included in each request (recommended now)
# "none"   -> each question is stateless
# "server" -> placeholder for future server-side conversation id (falls back to "client" if unsupported)
CONTEXT_MODE = os.getenv("EXPLAINER_CONTEXT_MODE", "client").lower()

# Rolling transcript limits (applies when CONTEXT_MODE != "none")
MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "8"))       # keep last N Q/A pairs
MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "24000"))   # hard cap to avoid token bloat

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
    1) Substitute {condition} (and any other vars) inside the question line itself.
    2) Return the concrete question string to inject into the main prompt as {question}.
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

# ---------------- OpenAI (Responses API) ----------------

_client = OpenAI()

def call_openai_responses(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = TEMPERATURE,  # kept for signature compatibility; not used
    *,
    conversation_block: Optional[str] = None,
    server_conversation_id: Optional[str] = None,
) -> str:
    """
    Call OpenAI Responses API with GPT-5-mini.
    NOTE: Do NOT pass 'temperature' (some SDK/model combos reject it).
    """
    max_tries = 6
    base_sleep = 1.0

    # Compose final input
    if conversation_block:
        preamble = (
            "You are answering a series of related questions for the same patient/context.\n"
            "Use the prior Q&A for consistency. Do not re-explain shared setup unless asked.\n\n"
            "=== Prior Q&A (most recent last) ===\n"
            f"{conversation_block}\n"
            "=== End prior Q&A ===\n\n"
        )
        final_input = f"{preamble}{prompt}"
    else:
        final_input = prompt

    for attempt in range(1, max_tries + 1):
        try:
            kwargs = dict(
                model=model,
                input=final_input,
            )
            # If/when the SDK exposes server-side conversation ids:
            # if server_conversation_id:
            #     kwargs["conversation_id"] = server_conversation_id

            resp = _client.responses.create(**kwargs)
            return resp.output_text.strip()

        except TypeError as e:
            # Defensive retry with bare minimum (in case any stray kwargs are added later)
            if attempt == 1 and "unexpected keyword argument" in str(e):
                try:
                    resp = _client.responses.create(model=model, input=final_input)
                    return resp.output_text.strip()
                except Exception:
                    pass
            if attempt == max_tries:
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.25 * (attempt - 1))
            logger.warning(f"⚠️ OpenAI TypeError (attempt {attempt}/{max_tries}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

        except Exception as e:
            if attempt == max_tries:
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.25 * (attempt - 1))
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

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
        # If it isn't valid JSON, just return the cleaned text
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
# (stored alongside outputs)
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
        Format last N Q/A into a human readable block.
        """
        if not self.qa:
            return ""
        subset = self.qa[-MAX_QA_IN_CONTEXT:]
        lines: List[str] = []
        for i, qa in enumerate(subset, 1):
            q = qa.get("q", "").strip()
            a = qa.get("a", "").strip()
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
                "temperature": TEMPERATURE,  # observed only
                "ctx": ctx,
                "questions_path": QUESTIONS_PATH,
                "prompt_path": PROMPT_PATH,
                "context_mode": CONTEXT_MODE,
                "max_qa_in_context": MAX_QA_IN_CONTEXT,
                "max_context_chars": MAX_CONTEXT_CHARS,
            },
        )
        ckpt = default_checkpoint()

        # Conversation state for this run
        convo = ConversationState()

        # Persist initial metadata (in the same folder as outputs)
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        # Sequential loop — only advance after successful write
        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            # 1) Fill {condition} (and any other ctx vars) inside the question itself
            filled_q = format_question(q_tmpl, ctx)

            # 2) Build full prompt with {question} + patient context
            base_prompt = build_prompt(prompt_template, filled_q, ctx)

            # 3) Conversation continuity
            conversation_block = ""
            server_conversation_id = None

            if CONTEXT_MODE == "client":
                conversation_block = convo.as_text_block()
            elif CONTEXT_MODE == "server":
                # Placeholder if/when your SDK exposes conversation_id.
                # server_conversation_id = convo.server_conversation_id
                # Fallback to client continuity for now:
                conversation_block = convo.as_text_block()

            # 4) Prepare output paths and manifest entry
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
            # Store convo snapshot for observability
            manifest["conversation_state"] = convo.to_dict()
            supabase_write_textjson(paths["manifest"], manifest)

            try:
                t0 = time.time()
                ai_text = call_openai_responses(
                    base_prompt,
                    model=payload.get("model", DEFAULT_MODEL),
                    temperature=TEMPERATURE,  # ignored by API
                    conversation_block=conversation_block if conversation_block else None,
                    server_conversation_id=server_conversation_id,
                )
                elapsed = round(time.time() - t0, 3)

                # Clean to pure JSON string (no markdown fences)
                final_output = clean_ai_output(ai_text)

                # Save as .txt but content is JSON/text
                supabase_write_txt(outfile, final_output)

                # Mark done
                item.update({"status": "done", "completed_at": now_iso(), "latency_seconds": elapsed})
                upsert_manifest_item(manifest, item)

                # Update conversation transcript (Q/A)
                if CONTEXT_MODE != "none":
                    convo.push(filled_q, final_output)

                # Persist manifest + checkpoint + convo snapshot
                manifest["conversation_state"] = convo.to_dict()
                supabase_write_textjson(paths["manifest"], manifest)

                ckpt = update_checkpoint(ckpt, idx)
                supabase_write_textjson(paths["checkpoint"], ckpt)

                # Politeness delay (tune/remove as needed)
                time.sleep(0.25)

            except Exception as e:
                item.update({
                    "status": "failed",
                    "failed_at": now_iso(),
                    "error": {"type": type(e).__name__, "message": str(e)},
                })
                upsert_manifest_item(manifest, item)
                manifest["conversation_state"] = convo.to_dict()
                supabase_write_textjson(paths["manifest"], manifest)
                # Continue to next question

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
    }, ensure_ascii=False))

    # Spin off background thread — return immediately to Zapier
    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
