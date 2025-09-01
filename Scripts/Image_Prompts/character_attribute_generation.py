# Scripts/Image_Prompts/character_attribute_generation.py

import os
import re
import json
import time
from typing import Dict, Any

import requests
from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =============================================================================
# Config
# =============================================================================

PROMPT_PATH = "Prompts/Image_Prompts/character_attributes.txt"

PARENT_DIR = "Explainer_Report/Ai_Responses/Question_Assets"
IMAGE_PROMPTS_SUBDIR = "Image_Prompts"
OUTPUT_FILENAME = "character_attributes.txt"

# Model config
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Supabase env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

# Retry policy
MAX_TRIES = 6
BASE_BACKOFF = 1.0  # seconds


# =============================================================================
# Helpers
# =============================================================================

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def safe_escape_braces(value: str) -> str:
    """Prevent .format collisions inside prompt templates."""
    return str(value or "").replace("{", "{{").replace("}", "}}")

def clean_ai_output_to_json_text(ai_text: str) -> str:
    """
    Strip ``` fences if present and pretty-print valid JSON; else return cleaned text.
    We don't enforce JSON strictly here—downstream may parse/validate as needed.
    """
    cleaned = (ai_text or "").strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        # Return raw if not valid JSON (logging for visibility)
        logger.warning("⚠️ AI output not valid JSON—writing raw text as received.")
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
# Core
# =============================================================================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expects JSON payload from Zapier with:
      {
        "run_id": "...",
        "condition": "...",
        "age": "...",
        "gender": "...",
        "ethnicity": "...",
        "region": "..."
      }
    """
    # ---- Required inputs
    run_id = (data.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Missing run_id in request payload")

    condition = data.get("condition", "")
    age       = data.get("age", "")
    gender    = data.get("gender", "")
    ethnicity = data.get("ethnicity", "")
    region    = data.get("region", "")

    logger.info("📥 character_attribute_generation.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        "condition": condition,
        "age": age,
        "gender": gender,
        "ethnicity": ethnicity,
        "region": region,
        "model": data.get("model", DEFAULT_MODEL)
    }, ensure_ascii=False))

    # ---- Load prompt template
    try:
        prompt_template = load_text(PROMPT_PATH)
    except FileNotFoundError:
        logger.error(f"❌ Prompt file not found at {PROMPT_PATH}")
        raise

    # ---- Inject variables
    prompt = prompt_template.format(
        condition=safe_escape_braces(condition),
        age=safe_escape_braces(age),
        gender=safe_escape_braces(gender),
        ethnicity=safe_escape_braces(ethnicity),
        region=safe_escape_braces(region),
        run_id=safe_escape_braces(run_id),
    )

    # ---- Call OpenAI
    ai_text = call_openai(prompt, model=data.get("model", DEFAULT_MODEL), temperature=TEMPERATURE)

    # ---- Clean to JSON-ish text (remove fences, pretty print if valid)
    json_text = clean_ai_output_to_json_text(ai_text)

    # ---- Save output to Supabase
    out_rel_path = f"{PARENT_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/{OUTPUT_FILENAME}"
    supabase_path = out_rel_path  # Engine.Files.write_supabase_file handles ROOT/Bucket
    logger.info(f"📤 Writing Character Attributes to: {supabase_path}")

    write_supabase_file(supabase_path, json_text, content_type="text/plain; charset=utf-8")

    return {
        "status": "ok",
        "run_id": run_id,
        "output_path": supabase_path
    }


# -----------------------------------------------------------------------------
# Optional: local debug entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Example local test payload (replace values as needed)
    test_payload = {
        "run_id": "TEST_RUN_ID_123",
        "condition": "Severe Osteoporosis",
        "age": "61",
        "gender": "Female",
        "ethnicity": "White: English, Welsh, Scottish, Northern Irish or British",
        "region": "United Kingdom",
        # "model": "gpt-4o"  # optional override
    }
    result = run_prompt(test_payload)
    print(json.dumps(result, indent=2))
