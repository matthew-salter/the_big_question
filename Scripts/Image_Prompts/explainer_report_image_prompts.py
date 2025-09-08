# Scripts/Image_Prompts/explainer_report_image_prompts.py

import os
import re
import json
import time
from typing import Dict, Any, List

import requests
from openai import OpenAI
from logger import logger
from Engine.Files.auth import get_supabase_headers
from Engine.Files.read_supabase_file import read_supabase_file
from Engine.Files.write_supabase_file import write_supabase_file

# =============================================================================
# Config
# =============================================================================

PROMPT_PATH = "Prompts/Image_Prompts/explainer_report_image_prompts.txt"

# Supabase paths (write_supabase_file prepends SUPABASE_ROOT_FOLDER automatically)
BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"
REPORT_ASSETS_SUBDIR = "Report_Assets"
IMAGE_PROMPTS_SUBDIR = "Image_Prompts"

# Model config
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Supabase env (for folder listing)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

# Retry policy
MAX_TRIES = 6
BASE_BACKOFF = 1.0  # seconds


# =============================================================================
# Helpers
# =============================================================================

def safe_escape_braces(value: str) -> str:
    """Protect accidental braces in injected strings before str.format()."""
    return str(value if value is not None else "").replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def list_supabase_folder(prefix: str) -> List[Dict[str, Any]]:
    """
    POST /storage/v1/object/list/{bucket}
    Body: {"prefix":"<path>/", "limit":1000, "offset":0, "sortBy":{"column":"name","order":"asc"}}
    Returns a list of objects with at least {"name": "..."}.
    """
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"

    full_prefix = f"{SUPABASE_ROOT_FOLDER}/{prefix}".rstrip("/") + "/"
    payload = {
        "prefix": full_prefix,
        "limit": 1000,
        "offset": 0,
        "sortBy": {"column": "name", "order": "asc"},
    }

    logger.info(f"📄 Listing Supabase folder: {payload['prefix']}")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    items = resp.json() or []
    logger.info(f"📂 Supabase returned {len(items)} entries for {payload['prefix']}")
    return items

def _normalize_quote_to_brace_spacing(text: str) -> str:
    """
    Ensure exactly one newline exists between the closing quote of the value and the closing brace:
        "...end."
    }
    This collapses 0+ blank lines/whitespace to exactly one newline, keeping your desired style.
    Safe because each value is a single-line string.
    """
    text = text.replace("\r\n", "\n")
    # Replace either same-line brace or multiple blank lines with exactly one newline before }
    text = re.sub(r'("\s*)(?:\n\s*)?}', r'"\n}', text)  # handles 0 or 1+ newlines -> 1 newline
    # If the model ever produced multiple newlines, collapse them to one (paranoia pass)
    text = re.sub(r'("\s*)\n{2,}\s*}', r'"\n}', text)
    return text

def clean_ai_output_to_json_text(ai_text: str) -> str:
    """
    Strip ``` fences; pretty-print JSON if parseable; else return cleaned raw.
    If the model returned multiple standalone JSON objects (non-parseable as one
    JSON value), normalize spacing so the closing brace is on its own line.
    """
    cleaned = (ai_text or "").strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        logger.warning("⚠️ AI output not valid JSON—writing raw text as received.")
        cleaned = _normalize_quote_to_brace_spacing(cleaned)
        return cleaned

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE) -> str:
    client = OpenAI()
    for attempt in range(1, MAX_TRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            if attempt == MAX_TRIES:
                logger.error(f"❌ OpenAI error (final attempt): {e}")
                raise
            sleep = BASE_BACKOFF * (2 ** (attempt - 1)) + 0.25 * (attempt - 1)
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{MAX_TRIES}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)


# =============================================================================
# Core worker
# =============================================================================

def _process_run(run_id: str, ctx: Dict[str, Any], prompt_template: str) -> None:
    """
    Heavy worker: read the single Report_Assets file, plus character_attributes,
    build one prompt, call OpenAI once, and write the result to Report_Prompts.txt.
    """
    try:
        logger.info(f"🚀 [ExplainerImagePrompts.Run] start run_id={run_id}")

        # ---- Load character attributes (required, like original script)
        char_path = f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/character_attributes.txt"
        logger.info(f"📥 Reading character attributes: {char_path}")
        character_attributes_text = read_supabase_file(char_path, binary=False) or ""
        character_attributes_text = character_attributes_text.strip()
        logger.info(f"🧩 character_attributes length={len(character_attributes_text)}")
        if not character_attributes_text:
            raise FileNotFoundError(f"Character attributes file empty or not found: {char_path}")

        # ---- Locate the single report assets file
        report_prefix = f"{BASE_DIR}/{run_id}/{REPORT_ASSETS_SUBDIR}"
        logger.info(
            f"📂 Looking for report assets under: {report_prefix} "
            f"(full: {SUPABASE_ROOT_FOLDER}/{report_prefix})"
        )
        try:
            entries = list_supabase_folder(report_prefix)
        except Exception as e:
            logger.exception(f"❌ Error listing Supabase folder: {report_prefix}: {e}")
            return

        files = [
            e.get("name", "") for e in entries
            if isinstance(e, dict) and e.get("name", "").lower().endswith(".txt")
        ]
        files_sorted = sorted(files)
        logger.info(f"📄 TXT files discovered ({len(files_sorted)}): {files_sorted}")

        if not files_sorted:
            logger.error(f"❌ No .txt files found in {report_prefix}")
            return

        if len(files_sorted) > 1:
            logger.warning("⚠️ Multiple files found in Report_Assets; using the first sorted name.")

        report_filename = files_sorted[0]
        report_rel = f"{report_prefix}/{report_filename}"

        # ---- Read the report assets content
        logger.info(f"📥 Reading report assets file: {report_rel}")
        try:
            report_assets_text = read_supabase_file(report_rel, binary=False) or ""
        except Exception as e:
            logger.exception(f"❌ Error reading report assets file {report_rel}: {e}")
            return

        report_assets_text = report_assets_text.strip()
        logger.info(f"🧾 report_assets length={len(report_assets_text)}")
        if not report_assets_text:
            logger.error(f"❌ Report assets file empty: {report_rel}")
            return

        # ---- Build prompt mapping
        mapping = {
            "character_attributes": safe_escape_braces(character_attributes_text),
            "report_assets": safe_escape_braces(report_assets_text),
            "condition": safe_escape_braces(ctx.get("condition", "")),
            "age": safe_escape_braces(ctx.get("age", "")),
            "gender": safe_escape_braces(ctx.get("gender", "")),
            "ethnicity": safe_escape_braces(ctx.get("ethnicity", "")),
            "region": safe_escape_braces(ctx.get("region", "")),
            "todays_date": safe_escape_braces(ctx.get("todays_date", "")),
            "run_id": safe_escape_braces(ctx.get("run_id", "")),
        }

        try:
            prompt = prompt_template.format(**mapping)
            logger.info(f"🧠 Built prompt (len={len(prompt)})")
        except Exception as e:
            logger.exception(f"❌ Error formatting prompt: {e}")
            return

        # ---- OpenAI call (single)
        try:
            t0 = time.time()
            ai_text = call_openai(
                prompt,
                model=ctx.get("model", DEFAULT_MODEL),
                temperature=TEMPERATURE
            )
            latency = round(time.time() - t0, 3)
            logger.info(f"🤖 OpenAI response received (latency={latency}s, len={len(ai_text or '')})")
        except Exception as e:
            logger.exception(f"❌ OpenAI call failed: {e}")
            return

        # ---- Clean to JSON text (no fences)
        final_text = clean_ai_output_to_json_text(ai_text)
        logger.info(f"🧹 Cleaned output (len={len(final_text)})")

        # ---- Save to Supabase
        out_rel = f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/Report_Prompts.txt"
        try:
            write_supabase_file(out_rel, final_text, content_type="text/plain; charset=utf-8")
            logger.info(f"📤 Wrote image prompts -> {out_rel}")
        except Exception as e:
            logger.exception(f"❌ Failed to write output to {out_rel}: {e}")
            return

        logger.info(f"✅ [ExplainerImagePrompts.Run] completed run_id={run_id}")

    except Exception as outer:
        logger.exception(f"❌ [ExplainerImagePrompts.Run] fatal for run_id={run_id}: {outer}")


# =============================================================================
# Entrypoint
# =============================================================================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called by main.py. Returns immediately so Zapier isn't held open.
    Spawns a background worker to generate a single set of image prompts for the report.
    """
    # ---- Required
    run_id = (data.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Missing run_id in request payload")

    # ---- Context mapping from Zapier payload
    ctx = {
        "condition": data.get("condition", ""),
        "age": data.get("age", ""),
        "gender": data.get("gender", ""),
        "ethnicity": data.get("ethnicity", ""),
        "region": data.get("region", ""),
        "todays_date": data.get("todays_date", ""),
        "run_id": run_id,
        "model": data.get("model", DEFAULT_MODEL),
    }

    logger.info("📥 explainer_report_image_prompts.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        "condition": ctx["condition"],
        "age": ctx["age"],
        "gender": ctx["gender"],
        "ethnicity": ctx["ethnicity"],
        "region": ctx["region"],
        "todays_date": ctx["todays_date"],
        "model": ctx["model"],
    }, ensure_ascii=False))

    # ---- Load prompt template once
    prompt_template = load_text(PROMPT_PATH)
    logger.info(f"📝 Loaded prompt template from {PROMPT_PATH} (len={len(prompt_template)})")

    # ---- Spawn background worker and RETURN IMMEDIATELY
    import threading
    t = threading.Thread(
        target=_process_run,
        args=(run_id, ctx, prompt_template),
        daemon=True,
    )
    t.start()
    logger.info(f"🚀 Background worker started for run_id={run_id}, thread={t.name}")

    # ---- Immediate response (so Zapier doesn't time out)
    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report image prompts generation started. Results will stream into Supabase.",
        "character_attributes_path": f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/character_attributes.txt",
        "report_assets_folder": f"{BASE_DIR}/{run_id}/{REPORT_ASSETS_SUBDIR}",
        "output_file": f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/Report_Prompts.txt"
    }


# -----------------------------------------------------------------------------
# Optional local test
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    test_payload = {
        "run_id": "TEST_RUN_ABC123",
        "condition": "Severe Osteoporosis",
        "age": "61",
        "gender": "Female",
        "ethnicity": "White: English, Welsh, Scottish, Northern Irish or British",
        "region": "United Kingdom",
        "todays_date": "01/09/2025",
        # "model": "gpt-4o"
    }
    res = run_prompt(test_payload)
    print(json.dumps(res, indent=2))
