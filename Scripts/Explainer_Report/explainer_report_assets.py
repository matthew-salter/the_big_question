# Scripts/Explainer_Report/explainer_report_assets.py

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

PROMPT_PATH = "Prompts/Explainer_Report/prompt_2_report_assets.txt"
AE_BE_PATH = "Prompts/American_to_British/american_to_british.txt"

PARENT_DIR = "Explainer_Report/Ai_Responses/Question_Assets"
MERGED_SUBDIR = "Merged_Question_Outputs"
REPORT_SUBDIR = "Report_Assets"

# Default to gpt-5-mini
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Supabase env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

# Retry policy
MAX_TRIES = 6
BASE_BACKOFF = 1.0  # seconds

# Reuse a single OpenAI client
_OPENAI_CLIENT = OpenAI()

# =============================================================================
# Helpers
# =============================================================================

def normalize_name(value: str) -> str:
    v = (value or "").strip()
    v = re.sub(r"[^\w\s\-]", "", v)
    v = re.sub(r"\s+", "_", v)
    return v or "Unknown"

def normalize_date_for_filename(value: str) -> str:
    v = (value or "").strip()
    v = v.replace("/", "-").replace(" ", "_").replace(":", "")
    return v or "date"

def safe_escape_braces(value: str) -> str:
    # Prevent .format collisions
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def list_supabase_folder(prefix: str) -> List[Dict[str, Any]]:
    """
    POST /storage/v1/object/list/{bucket}
    Body: {"prefix":"<path>/", "limit":1000, "offset":0, "sortBy":{"column":"name","order":"asc"}}
    """
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"

    payload = {
        "prefix": f"{SUPABASE_ROOT_FOLDER}/{prefix}".rstrip("/") + "/",
        "limit": 1000,
        "offset": 0,
        "sortBy": {"column": "name", "order": "asc"},
    }

    logger.info(f"📄 Listing Supabase folder: {payload['prefix']}")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    return resp.json() or []

# ---------------- AE → BE conversion ----------------

_PAIR_RE = re.compile(r'"([^"]+)"\s*:\s*"([^"]+)"')

def load_ae_be_mapping(path: str) -> Dict[str, str]:
    """
    Parse tolerant '"American": "British"' lines.
    Duplicates allowed; last one wins.
    """
    try:
        text = load_text(path)
    except FileNotFoundError:
        logger.warning(f"⚠️ AE→BE mapping not found at {path}; skipping conversion.")
        return {}

    mapping: Dict[str, str] = {}
    for m in _PAIR_RE.finditer(text):
        mapping[m.group(1)] = m.group(2)

    logger.info(f"🇺🇸→🇬🇧 Loaded {len(mapping)} AE→BE replacements from {path}")
    return mapping

def compile_ae_be_regex(mapping: Dict[str, str]):
    """
    Build a regex that matches any American term as a whole word.
    """
    if not mapping:
        return None, mapping
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)"
    return re.compile(pattern), mapping

def american_to_british(text: str, compiled) -> str:
    if not compiled or not compiled[0]:
        return text
    pattern, mapping = compiled
    return pattern.sub(lambda m: mapping.get(m.group(1), m.group(1)), text)

# ---------------- OpenAI (Responses API; gpt-5-mini-safe) ----------------

def _extract_output_text(resp) -> str:
    """
    Robustly extract output text from Responses API response.
    """
    text_out = getattr(resp, "output_text", None)
    if text_out:
        return text_out.strip()

    # Fallback traversal (older SDK shims)
    try:
        if hasattr(resp, "output") and resp.output:
            first = resp.output[0]
            if hasattr(first, "content") and first.content:
                node = first.content[0]
                if hasattr(node, "text") and node.text:
                    return node.text.strip()
    except Exception:
        pass

    raise ValueError("Empty response from model")

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE) -> str:
    """
    Uses Responses API. Some models (e.g., gpt-5-mini) reject 'temperature'.
    We auto-retry once without temperature if we see that error.
    """
    client = _OPENAI_CLIENT
    temp_allowed = True  # optimistic; flip off if API complains

    for attempt in range(1, MAX_TRIES + 1):
        try:
            kwargs: Dict[str, Any] = {"model": model, "input": prompt}
            if temp_allowed:
                kwargs["temperature"] = temperature

            resp = client.responses.create(**kwargs)
            return _extract_output_text(resp)

        except Exception as e:
            msg = str(e)
            # Immediate fix-up for "Unsupported parameter: 'temperature'"
            if "Unsupported parameter: 'temperature'" in msg or "param': 'temperature'" in msg:
                if temp_allowed:
                    logger.warning("♻️ Model does not support 'temperature'. Retrying without it.")
                    temp_allowed = False
                    # retry immediately (do not count against backoff budget)
                    try:
                        resp = client.responses.create(model=model, input=prompt)
                        return _extract_output_text(resp)
                    except Exception as e2:
                        # fall through to normal backoff handling
                        msg = str(e2)

            if attempt == MAX_TRIES:
                raise
            sleep = BASE_BACKOFF * (2 ** (attempt - 1)) + 0.25 * (attempt - 1)
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{MAX_TRIES}): {e}. Backing off {sleep:.2f}s")
            time.sleep(sleep)

def clean_ai_output_to_json_text(ai_text: str) -> str:
    """
    Strip ``` fences if present and pretty-print valid JSON; else return cleaned text.
    """
    cleaned = ai_text.strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return cleaned

# =============================================================================
# Core
# =============================================================================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expects JSON payload from Zapier with:
      {
        "run_id": "...",
        "first_name": "...",
        "sur_name": "...",
        "condition": "...",
        "age": "...",
        "gender": "...",
        "ethnicity": "...",
        "region": "...",
        "todays_date": "08/07/25 04:44PM"
      }
    """
    # ---- Inputs
    run_id = data.get("run_id")
    if not run_id:
        raise ValueError("Missing run_id in request payload")

    first_name = data.get("first_name", "")
    sur_name   = data.get("sur_name", "")
    condition  = data.get("condition", "")
    age        = data.get("age", "")
    gender     = data.get("gender", "")
    ethnicity  = data.get("ethnicity", "")
    region     = data.get("region", "")
    todays_date = data.get("todays_date", "")

    logger.info("📥 explainer_report_assets.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id, "first_name": first_name, "sur_name": sur_name,
        "condition": condition, "age": age, "gender": gender,
        "ethnicity": ethnicity, "region": region, "todays_date": todays_date,
        "model": data.get("model", DEFAULT_MODEL)
    }, ensure_ascii=False))

    # ---- Locate the merged file (there should be exactly one)
    merged_dir = f"{PARENT_DIR}/{run_id}/{MERGED_SUBDIR}"
    items = list_supabase_folder(merged_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it and it["name"].lower().endswith(".txt")]

    if not names:
        raise FileNotFoundError(f"No merged .txt file found under {merged_dir}")

    if len(names) > 1:
        logger.warning(f"⚠️ More than one merged file found; taking the first alphabetically: {names[0]}")

    merged_file_rel = f"{merged_dir}/{names[0]}"
    logger.info(f"📥 Reading merged question assets: {merged_file_rel}")
    question_assets_text = read_supabase_file(merged_file_rel, binary=False) or ""
    question_assets_text = question_assets_text.strip()

    # ---- Build prompt: inject vars + merged text (as {question_assets})
    prompt_template = load_text(PROMPT_PATH)
    prompt = prompt_template.format(
        condition=safe_escape_braces(condition),
        age=safe_escape_braces(age),
        gender=safe_escape_braces(gender),
        ethnicity=safe_escape_braces(ethnicity),
        region=safe_escape_braces(region),
        todays_date=safe_escape_braces(todays_date),
        run_id=safe_escape_braces(run_id),
        question_assets=safe_escape_braces(question_assets_text),
    )

    # ---- Call OpenAI
    ai_text = call_openai(prompt, model=data.get("model", DEFAULT_MODEL), temperature=TEMPERATURE)

    # ---- Clean to JSON text (no fences)
    json_text = clean_ai_output_to_json_text(ai_text)

    # ---- AE → BE conversion
    mapping = load_ae_be_mapping(AE_BE_PATH)
    compiled = compile_ae_be_regex(mapping)
    json_text_be = american_to_british(json_text, compiled)

    # ---- Save output
    report_dir = f"{PARENT_DIR}/{run_id}/{REPORT_SUBDIR}"
    first = normalize_name(first_name)
    last  = normalize_name(sur_name)
    cond  = normalize_name(condition)
    date_seg = normalize_date_for_filename(todays_date)
    out_name = f"{first}_{last}_{cond}_Report_Assets_{date_seg}.txt"
    out_path = f"{report_dir}/{out_name}"

    logger.info(f"📤 Writing Report Assets to: {out_path}")
    write_supabase_file(out_path, json_text_be, content_type="text/plain; charset=utf-8")

    return {
        "status": "ok",
        "run_id": run_id,
        "output_path": out_path
    }
