# Scripts/Explainer_Report/merge_image_prompts.py

import os
import re
import json
from typing import Dict, Any, List, Tuple

import requests
from logger import logger
from Engine.Files.auth import get_supabase_headers
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

PARENT_DIR = "Explainer_Report/Ai_Responses/Question_Assets"
IMAGE_PROMPTS_SUBDIR = "Image_Prompts"
MERGED_IMAGE_PROMPTS_SUBDIR = "Merged_Image_Prompts"

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def list_supabase_folder(prefix: str) -> List[Dict[str, Any]]:
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

    logger.info(f"📂 Listing Supabase folder: {payload['prefix']}")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    return resp.json() or []

# Accept many variants: "Question_01.txt", "Question 1.txt", "QUESTION-12.txt",
# or files that contain 'Question_7' somewhere before '.txt'.
_QNUM_PRIMARY = re.compile(r'(?i)^question[\s_\-]*([0-9]+)\.txt$')
_QNUM_NEAR_END = re.compile(r'(?i)question.*?([0-9]+)\.txt$')
_ANY_DIGITS     = re.compile(r'([0-9]+)')

def extract_question_index_and_str(filename: str) -> Tuple[int, str, bool]:
    """
    Try several patterns to extract a question number from filename.
    Returns (numeric_index, zero_padded_str, matched_flag).
    """
    name = filename.strip()

    m = _QNUM_PRIMARY.search(name)
    if not m:
        m = _QNUM_NEAR_END.search(name)
    if not m:
        # Last chance: any digits in the name
        m = _ANY_DIGITS.search(name)

    if m:
        try:
            n = int(m.group(1))
            return n, f"{n:02d}", True
        except ValueError:
            pass
    return 10**9, "", False

def normalize_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^\w\s\-]", "", value)
    value = re.sub(r"\s+", "_", value)
    return value or "Unknown"

def normalize_date_for_filename(value: str) -> str:
    v = (value or "").strip()
    v = v.replace("/", "-").replace(":", "")
    v = re.sub(r"\s+", "_", v)
    return v or "date"

def should_skip_filename(name: str) -> bool:
    return name.lower() == "character_attributes.txt"

def add_question_number_to_snippet(raw_text: str, qnum_str: str) -> str:
    """
    Insert 'Question_Number' into a JSON snippet.
    Prefer JSON parse/re-serialize; fallback to text insertion if JSON is malformed.
    """
    if not qnum_str:
        return raw_text

    text = (raw_text or "")
    # Strip potential BOM to help json.loads
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Put Question_Number first
            new_obj = {"Question_Number": qnum_str}
            # If it existed, overwrite with canonical value
            if "Question_Number" in data:
                data.pop("Question_Number", None)
            new_obj.update(data)
            return json.dumps(new_obj, ensure_ascii=False, indent=2)
        # Not a dict → fallback
    except Exception:
        pass

    # Text fallback: insert after first '{' if present
    stripped = text.lstrip()
    if stripped.startswith("{"):
        return text.replace("{", "{\n  \"Question_Number\": \"" + qnum_str + "\",", 1)
    return text

# -------------------------------------------------------------------
# Core
# -------------------------------------------------------------------

def merge_image_prompts(run_id: str, first_name: str, sur_name: str,
                        condition: str, todays_date: str) -> Dict[str, Any]:
    """
    Merge all image prompt .txt files for a given run_id into a single text file.
    Injects "Question_Number": "NN" based on the filename. If no number can be
    extracted, assigns sequential numbers in sorted order.
    """
    src_dir = f"{PARENT_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}"
    out_dir = f"{PARENT_DIR}/{run_id}/{MERGED_IMAGE_PROMPTS_SUBDIR}"

    items = list_supabase_folder(src_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]

    # Consider only .txt files and skip the attributes file
    txt_names = [
        n for n in names
        if n.lower().endswith(".txt") and not should_skip_filename(n)
    ]

    if not txt_names:
        raise FileNotFoundError(
            f"No .txt files (excluding character_attributes.txt) found under {src_dir}"
        )

    # Sort deterministically: by (detected index if any, then filename)
    sort_keys: List[Tuple[int, str]] = []
    for n in txt_names:
        idx, _, _ = extract_question_index_and_str(n)
        sort_keys.append((idx, n.lower()))
    txt_names = [n for _, n in sorted(zip(sort_keys, txt_names), key=lambda t: t[0])]

    logger.info(f"🖼️ Found {len(txt_names)} image prompt files to merge.")

    merged_chunks: List[str] = []
    injected_count = 0
    seq_assigned = 0
    parse_fallback_used = 0
    detected_numbers: List[str] = []

    # First pass: detect numbers (for logging) and see who needs sequential fallback
    detected = []
    for n in txt_names:
        idx, s, matched = extract_question_index_and_str(n)
        detected.append((n, idx, s, matched))

    # Determine sequential counter for those with no match
    seq = 1
    for n, idx, s, matched in detected:
        rel_path = f"{src_dir}/{n}"
        logger.info(f"📥 Reading: {rel_path}")

        content = read_supabase_file(rel_path, binary=False)
        if content is None:
            logger.warning(f"⚠️ No content in {rel_path}; skipping.")
            continue
        content = content.rstrip()

        if matched:
            qnum_str = s
            detected_numbers.append(qnum_str)
        else:
            qnum_str = f"{seq:02d}"
            seq += 1
            seq_assigned += 1
            detected_numbers.append(qnum_str)
            logger.info(f"   ↳ No number detected in '{n}', assigned sequential: {qnum_str}")

        processed_before = content
        processed_after = add_question_number_to_snippet(processed_before, qnum_str)
        if processed_after != processed_before:
            injected_count += 1
        else:
            # If unchanged, try one more robust path: force JSON parse after trimming BOM/whitespace
            try:
                txt = processed_before.lstrip("\ufeff").strip()
                data = json.loads(txt)
                if isinstance(data, dict):
                    data.pop("Question_Number", None)
                    data = {"Question_Number": qnum_str, **data}
                    processed_after = json.dumps(data, ensure_ascii=False, indent=2)
                    injected_count += 1
                else:
                    parse_fallback_used += 1
            except Exception:
                parse_fallback_used += 1

        merged_chunks.append(processed_after)

    if not merged_chunks:
        raise ValueError("All matched .txt files were empty; nothing to merge.")

    merged_text = "\n".join(merged_chunks) + "\n"

    # Build output filename
    first = normalize_name(first_name)
    last = normalize_name(sur_name)
    cond = normalize_name(condition)
    date_seg = normalize_date_for_filename(todays_date)

    out_name = f"{first}_{last}_{cond}_Merged_Image_Prompts_{date_seg}.txt"
    out_path = f"{out_dir}/{out_name}"

    # Write to Supabase
    logger.info(f"📤 Writing merged image prompts file: {out_path}")
    write_supabase_file(out_path, merged_text, content_type="text/plain; charset=utf-8")

    return {
        "status": "ok",
        "run_id": run_id,
        "files_considered": len(names),
        "files_eligible": len(txt_names),
        "files_merged": len(merged_chunks),
        "ignored_files": [n for n in names if should_skip_filename(n)],
        "question_numbers_detected": detected_numbers,
        "question_numbers_injected": injected_count,
        "sequential_numbers_assigned": seq_assigned,
        "parse_fallback_used": parse_fallback_used,
        "output_path": out_path,
    }

# -------------------------------------------------------------------
# Public entrypoint for main.py
# -------------------------------------------------------------------

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected JSON payload from Zapier:
      {
        "run_id": "...",
        "first_name": "Elizabeth",
        "sur_name": "Salter",
        "condition": "Dementia",
        "todays_date": "09/01/25 01:22PM"
      }
    """
    run_id = (data.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")

    first_name = data.get("first_name", "")
    sur_name = data.get("sur_name", "")
    condition = data.get("condition", "")
    todays_date = data.get("todays_date", "")

    logger.info(
        f"🧩 merge_image_prompts.run_prompt: run_id={run_id}, "
        f"first_name={first_name}, sur_name={sur_name}, "
        f"condition={condition}, todays_date={todays_date}"
    )

    return merge_image_prompts(
        run_id=run_id,
        first_name=first_name,
        sur_name=sur_name,
        condition=condition,
        todays_date=todays_date,
    )
