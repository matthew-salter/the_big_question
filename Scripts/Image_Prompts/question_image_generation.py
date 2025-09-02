# Scripts/Image_Prompts/question_image_generation.py

import os
import re
import json
import time
from typing import Dict, Any, List, Tuple

import requests
from openai import OpenAI
from logger import logger
from Engine.Files.auth import get_supabase_headers
from Engine.Files.read_supabase_file import read_supabase_file
from Engine.Files.write_supabase_file import write_supabase_file

# =============================================================================
# Config
# =============================================================================

PROMPT_PATH = "Prompts/Image_Prompts/question_image_generation.txt"

# Supabase paths (write_supabase_file prepends SUPABASE_ROOT_FOLDER automatically)
BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"
QUESTION_SUBDIR = "Individual_Question_Outputs"
IMAGE_PROMPTS_SUBDIR = "Image_Prompts"

# Model config
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Supabase env (for folder listing)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

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

    # IMPORTANT: include the root folder so we list the correct directory
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

def parse_question_number(filename: str) -> int:
    """
    Extract leading integer from filenames like '01_question-title_xxxxx.txt'.
    Returns -1 if not matched.
    """
    m = _QFILE_RE.match(filename)
    if not m:
        return -1
    try:
        return int(m.group(1))
    except ValueError:
        return -1

def is_every_4th_question(qnum: int) -> bool:
    """
    True for 1,5,9,13,... i.e., (n-1) % 4 == 0
    """
    return qnum >= 1 and ((qnum - 1) % 4 == 0)

def zero_pad(n: int, width: int = 2) -> str:
    return f"{n:0{width}d}"

def clean_ai_output_to_json_text(ai_text: str) -> str:
    """
    Strip ``` fences; pretty-print JSON if parseable; else return cleaned raw.
    """
    cleaned = (ai_text or "").strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
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
        "region": "...",
        "todays_date": "DD/MM/YYYY",
        "model": "gpt-4o" (optional)
      }
    Creates image prompt files for every 4th question (1,5,9,...) under:
      Explainer_Report/Ai_Responses/Question_Assets/{run_id}/Image_Prompts/Question_{NN}.txt
    """
    # ---- Required
    run_id = (data.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Missing run_id in request payload")

    # ---- Patient/context mapping
    ctx = {
        "condition": data.get("condition", ""),
        "age": data.get("age", ""),
        "gender": data.get("gender", ""),
        "ethnicity": data.get("ethnicity", ""),
        "region": data.get("region", ""),
        "todays_date": data.get("todays_date", ""),
        "run_id": run_id,
    }

    logger.info("📥 question_image_generation.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        **ctx,
        "model": data.get("model", DEFAULT_MODEL),
    }, ensure_ascii=False))

    # ---- Load character attributes (JSON snippet stored as .txt)
    char_path = f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/character_attributes.txt"
    logger.info(f"📥 Reading character attributes: {char_path}")
    character_attributes_text = read_supabase_file(char_path, binary=False) or ""
    character_attributes_text = character_attributes_text.strip()
    logger.info(f"🧩 character_attributes length={len(character_attributes_text)}")
    if not character_attributes_text:
        raise FileNotFoundError(f"Character attributes file empty or not found: {char_path}")

    # ---- List question files and select every 4th
    questions_prefix = f"{BASE_DIR}/{run_id}/{QUESTION_SUBDIR}"
    logger.info(
        f"📂 Looking for question files under: {questions_prefix} "
        f"(full: {SUPABASE_ROOT_FOLDER}/{questions_prefix})"
    )
    entries = list_supabase_folder(questions_prefix)

    try:
        entries = list_supabase_folder(questions_prefix)
        logger.info(f"📂 Supabase returned {len(entries)} entries")
    except Exception as e:
        logger.exception(f"❌ Error listing Supabase folder: {questions_prefix}: {e}")
        raise

    files = [
        e.get("name", "") for e in entries
        if isinstance(e, dict) and e.get("name", "").lower().endswith(".txt")
    ]
    logger.info(f"📄 TXT files discovered ({len(files)}): {files}")

    # Parse question numbers and sort by numeric order
    numbered: List[Tuple[int, str]] = []
    for name in files:
        qnum = parse_question_number(name)
        logger.info(f"🔎 Parsed qnum={qnum} from file='{name}'")
        if qnum > 0:
            numbered.append((qnum, name))
        else:
            logger.warning(f"⚠️ Could not parse question number from: {name}")

    numbered.sort(key=lambda x: x[0])
    logger.info(f"📊 Numbered files (sorted): {numbered}")

    # Filter to every 4th: 1,5,9,...
    targets = [(q, n) for (q, n) in numbered if is_every_4th_question(q)]
    logger.info(f"🎯 Files selected (every 4th): {targets}")
    if not targets:
        logger.warning("⚠️ No question files matched the every-4th rule (1,5,9,...)")

    # ---- Load prompt template
    prompt_template = load_text(PROMPT_PATH)
    logger.info(f"📝 Loaded prompt template from {PROMPT_PATH} (len={len(prompt_template)})")

    # ---- Process each selected question
    outputs = []
    for qnum, fname in targets:
        q_rel = f"{questions_prefix}/{fname}"
        logger.info(f"📥 Reading question file: {q_rel}")
        try:
            question_text = read_supabase_file(q_rel, binary=False) or ""
        except Exception as e:
            logger.exception(f"❌ Error reading question file {q_rel}: {e}")
            continue

        question_text = question_text.strip()
        logger.info(f"🧾 question_text length={len(question_text)} for qnum={qnum}")
        if not question_text:
            logger.warning(f"⚠️ Skipping empty question file: {q_rel}")
            continue

        # ---- Build prompt
        mapping = {
            "character_attributes": safe_escape_braces(character_attributes_text),
            "question_assets": safe_escape_braces(question_text),
            "condition": safe_escape_braces(ctx["condition"]),
            "age": safe_escape_braces(ctx["age"]),
            "gender": safe_escape_braces(ctx["gender"]),
            "ethnicity": safe_escape_braces(ctx["ethnicity"]),
            "region": safe_escape_braces(ctx["region"]),
            "todays_date": safe_escape_braces(ctx["todays_date"]),
            "run_id": safe_escape_braces(ctx["run_id"]),
        }

        try:
            prompt = prompt_template.format(**mapping)
            logger.info(f"🧠 Built prompt for Q{qnum} (len={len(prompt)})")
        except KeyError as e:
            missing = str(e).strip("'")
            logger.error(f"❌ Prompt template missing value for {{{missing}}}; skipping Q{qnum}")
            continue
        except Exception as e:
            logger.exception(f"❌ Error formatting prompt for Q{qnum}: {e}")
            continue

        # ---- Call OpenAI
        try:
            t0 = time.time()
            ai_text = call_openai(prompt, model=data.get("model", DEFAULT_MODEL), temperature=TEMPERATURE)
            latency = round(time.time() - t0, 3)
            logger.info(f"🤖 OpenAI response for Q{qnum} received (latency={latency}s, len={len(ai_text or '')})")
        except Exception as e:
            logger.exception(f"❌ OpenAI call failed for Q{qnum}: {e}")
            continue

        # ---- Clean to JSON text (no fences)
        final_text = clean_ai_output_to_json_text(ai_text)
        logger.info(f"🧹 Cleaned output for Q{qnum} (len={len(final_text)})")

        # ---- Save to Supabase
        qnum_str = zero_pad(qnum, 2 if qnum < 100 else 3)
        out_rel = f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/Question_{qnum_str}.txt"
        try:
            write_supabase_file(out_rel, final_text, content_type="text/plain; charset=utf-8")
            logger.info(f"📤 Wrote image prompt for Q{qnum} -> {out_rel}")
        except Exception as e:
            logger.exception(f"❌ Failed to write output for Q{qnum} to {out_rel}: {e}")
            continue

        outputs.append({"qnum": qnum, "output_path": out_rel})

        # Optional small delay
        time.sleep(0.2)

    logger.info(f"✅ Processing complete: processed={len(outputs)} for run_id={run_id}")

    return {
        "status": "ok",
        "run_id": run_id,
        "processed": len(outputs),
        "items": outputs,
        "character_attributes_path": char_path,
        "question_folder": questions_prefix,
        "output_folder": f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/"
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
