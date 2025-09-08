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
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

# Retry policy
MAX_TRIES = 6
BASE_BACKOFF = 1.0  # seconds


# =============================================================================
# Helpers
# =============================================================================

# Regex to capture leading question number (1_, 01_, 123_, etc.)
_QFILE_RE = re.compile(r"^(\d+)_")

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

def _process_run(
    run_id: str,
    ctx: Dict[str, Any],
    prompt_template: str,
    character_attributes_text: str,
    questions_prefix: str,
    targets: List[Tuple[int, str]],
) -> None:
    """
    Heavy worker: for each selected question file, build a prompt, call OpenAI,
    and write the result to Supabase.
    """
    try:
        logger.info(f"🚀 [ImagePrompts.Run] start run_id={run_id}, targets={len(targets)}")

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

            # ---- Build prompt mapping
            mapping = {
                "character_attributes": safe_escape_braces(character_attributes_text),
                "question_assets": safe_escape_braces(question_text),
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
                logger.info(f"🧠 Built prompt for Q{qnum} (len={len(prompt)})")
            except Exception as e:
                logger.exception(f"❌ Error formatting prompt for Q{qnum}: {e}")
                continue

            # ---- OpenAI call
            try:
                t0 = time.time()
                ai_text = call_openai(
                    prompt,
                    model=ctx.get("model", DEFAULT_MODEL),
                    temperature=TEMPERATURE
                )
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

            # Politeness delay to avoid hammering APIs
            time.sleep(0.2)

        logger.info(f"✅ [ImagePrompts.Run] completed run_id={run_id}, generated={len(targets)}")

    except Exception as outer:
        logger.exception(f"❌ [ImagePrompts.Run] fatal for run_id={run_id}: {outer}")


def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called by main.py. Returns immediately so Zapier isn't held open.
    Spawns a background worker to generate image prompts for every 4th question.
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
        "model": data.get("model", DEFAULT_MODEL),
    }

    logger.info("📥 question_image_generation.run_prompt payload:")
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

    # ---- Load character attributes (JSON snippet stored as .txt)
    char_path = f"{BASE_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}/character_attributes.txt"
    logger.info(f"📥 Reading character attributes: {char_path}")
    character_attributes_text = read_supabase_file(char_path, binary=False) or ""
    character_attributes_text = character_attributes_text.strip()
    logger.info(f"🧩 character_attributes length={len(character_attributes_text)}")
    if not character_attributes_text:
        raise FileNotFoundError(f"Character attributes file empty or not found: {char_path}")

    # ---- List question files (correct folder) and select every 4th
    questions_prefix = f"{BASE_DIR}/{run_id}/{QUESTION_SUBDIR}"
    logger.info(
        f"📂 Looking for question files under: {questions_prefix} "
        f"(full: {SUPABASE_ROOT_FOLDER}/{questions_prefix})"
    )
    try:
        entries = list_supabase_folder(questions_prefix)
        logger.info(f"📂 Supabase returned {len(entries)} entries for {SUPABASE_ROOT_FOLDER}/{questions_prefix}")
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
    selected_qnums = [q for q, _ in targets]
    logger.info(f"🎯 Files selected (every 4th): {targets}")
    if not targets:
        logger.warning("⚠️ No question files matched the every-4th rule (1,5,9,...)")

    # ---- Load prompt template once
    prompt_template = load_text(PROMPT_PATH)
    logger.info(f"📝 Loaded prompt template from {PROMPT_PATH} (len={len(prompt_template)})")

    # ---- Spawn background worker and RETURN IMMEDIATELY
    import threading
    t = threading.Thread(
        target=_process_run,
        args=(run_id, ctx, prompt_template, character_attributes_text, questions_prefix, targets),
        daemon=True,
    )
    t.start()
    logger.info(f"🚀 Background worker started for run_id={run_id}, thread={t.name}")

    # ---- Immediate response (so Zapier doesn't time out)
    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Question image generation started. Results will stream into Supabase.",
        "character_attributes_path": char_path,
        "question_folder": questions_prefix,
        "selected_count": len(targets),
        "selected_qnums": selected_qnums,
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
