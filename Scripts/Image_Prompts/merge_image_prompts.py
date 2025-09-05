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

_QNUM_RE = re.compile(r"(?i)\bquestion[_\- ]?(\d+)\.txt$")

def extract_question_index_and_str(filename: str) -> Tuple[int, str]:
    """
    Returns (numeric_index_for_sort, zero-padded string e.g. '01').
    Non-matching: (large_number, '').
    """
    m = _QNUM_RE.search(filename)
    if m:
        try:
            n = int(m.group(1))
            s = f"{n:02d}"  # zero-pad to 2 (01, 05, 12, ...)
            return n, s
        except ValueError:
            pass
    return 10**9, ""

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
    Try to parse JSON and inject 'Question_Number' as the first key.
    Fallback: text insertion right after the opening '{'.
    Always returns a string (pretty-printed JSON if parsing succeeded).
    """
    if not qnum_str:
        return raw_text

    try:
        data = json.loads(raw_text)
        # Prepend Question_Number while preserving order
        if isinstance(data, dict):
            # If already present, overwrite to the canonical value
            if "Question_Number" in data:
                data["Question_Number"] = qnum_str
                return json.dumps(data, ensure_ascii=False, indent=2)

            new_obj = {"Question_Number": qnum_str}
            # Extend with the rest (insertion order preserved in Python 3.7+)
            new_obj.update(data)
            return json.dumps(new_obj, ensure_ascii=False, indent=2)
        else:
            # Not a dict—fallback to text insertion
            raise ValueError("Top-level JSON is not an object")
    except Exception:
        # Text fallback: insert after first '{'
        # Ensure a comma to remain valid JSON if the rest starts with a key
        stripped = raw_text.lstrip()
        if stripped.startswith("{"):
            # Insert with newline + two-space indent, trailing comma
            insertion = f'\n  "Question_Number": "{qnum_str}",'
            return raw_text.replace("{", "{" + insertion, 1)
        return raw_text

# -------------------------------------------------------------------
# Core
# -------------------------------------------------------------------

def merge_image_prompts(run_id: str, first_name: str, sur_name: str,
                        condition: str, todays_date: str) -> Dict[str, Any]:
    """
    Merge all image prompt .txt files for a given run_id into a single text file.
    Injects "Question_Number": "NN" based on the filename 'Question_NN.txt'.
    Ignores 'character_attributes.txt'. Concatenates with a single newline between files.
    """
    src_dir = f"{PARENT_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}"
    out_dir = f"{PARENT_DIR}/{run_id}/{MERGED_IMAGE_PROMPTS_SUBDIR}"

    items = list_supabase_folder(src_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]

    # Filter to .txt files excluding character_attributes
    txt_names = [
        n for n in names
        if n.lower().endswith(".txt") and not should_skip_filename(n)
    ]

    if not txt_names:
        raise FileNotFoundError(
            f"No .txt files (excluding character_attributes.txt) found under {src_dir}"
        )

    # Sort by extracted question number (fallback alpha)
    txt_names.sort(key=lambda n: (extract_question_index_and_str(n)[0], n.lower()))

    logger.info(f"🖼️ Found {len(txt_names)} image prompt files to merge.")

    merged_chunks: List[str] = []
    injected_count = 0
    already_had_field = 0
    parse_fail_fallback = 0

    for fname in txt_names:
        rel_path = f"{src_dir}/{fname}"
        qnum_idx, qnum_str = extract_question_index_and_str(fname)

        logger.info(f"📥 Reading: {rel_path} (qnum='{qnum_str or '-'}')")
        content = read_supabase_file(rel_path, binary=False)
        content = (content or "").rstrip()
        if not content:
            logger.warning(f"⚠️ Empty content in {rel_path}; skipping.")
            continue

        # Try JSON path first (to count metrics)
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if data.get("Question_Number") is None:
                    data = {"Question_Number": qnum_str} | data  # Python 3.9+ dict union
                    injected_count += 1
                else:
                    # Overwrite to canonical value for consistency
                    data["Question_Number"] = qnum_str
                    already_had_field += 1
                processed = json.dumps(data, ensure_ascii=False, indent=2)
            else:
                raise ValueError("Top-level JSON is not an object")
        except Exception:
            # Fallback to safe text insertion
            processed = add_question_number_to_snippet(content, qnum_str)
            parse_fail_fallback += 1

        merged_chunks.append(processed)

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
        "question_numbers_injected": injected_count,
        "question_numbers_preserved": already_had_field,
        "regex_fallback_used": parse_fail_fallback,
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
