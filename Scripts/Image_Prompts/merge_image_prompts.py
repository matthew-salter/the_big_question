# Scripts/Explainer_Report/merge_image_prompts.py

import os
import re
import json
from typing import Dict, Any, List

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
    """
    List objects within a Supabase storage 'folder' (prefix).
    Returns a list of dicts with at least a 'name' key.
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

    logger.info(f"📂 Listing Supabase folder: {payload['prefix']}")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    return resp.json() or []

_QNUM_RE = re.compile(r"(?i)\bquestion[_\- ]?(\d+)\.txt$")

def extract_question_index(filename: str) -> int:
    """
    Extract numeric index from filenames like 'Question_01.txt'.
    Returns a large number if no match (so they sort to the end).
    """
    m = _QNUM_RE.search(filename)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 10**9  # non-matching files go last

def normalize_name(value: str) -> str:
    """
    Safe segment for filenames: strip, remove non-word chars except spaces/hyphens,
    collapse spaces to underscores.
    """
    value = (value or "").strip()
    value = re.sub(r"[^\w\s\-]", "", value)
    value = re.sub(r"\s+", "_", value)
    return value or "Unknown"

def normalize_date_for_filename(value: str) -> str:
    """
    Safe date segment: replace slashes with dashes; remove colons; collapse spaces to underscore.
    e.g. '09/01/25 01:22PM' -> '09-01-25_0122PM'
    """
    v = (value or "").strip()
    v = v.replace("/", "-").replace(":", "")
    v = re.sub(r"\s+", "_", v)
    return v or "date"

def should_skip_filename(name: str) -> bool:
    """
    Return True if this file should be ignored (only 'character_attributes.txt').
    Comparison is case-insensitive and requires exact filename.
    """
    return name.lower() == "character_attributes.txt"

# -------------------------------------------------------------------
# Core
# -------------------------------------------------------------------

def merge_image_prompts(run_id: str, first_name: str, sur_name: str,
                        condition: str, todays_date: str) -> Dict[str, Any]:
    """
    Merge all image prompt .txt files for a given run_id into a single text file.
    Ignores 'character_attributes.txt'. Concatenates with a single newline between files.
    """
    # Resolve folders
    src_dir = f"{PARENT_DIR}/{run_id}/{IMAGE_PROMPTS_SUBDIR}"
    out_dir = f"{PARENT_DIR}/{run_id}/{MERGED_IMAGE_PROMPTS_SUBDIR}"

    # List files in the source folder
    items = list_supabase_folder(src_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]

    # Only consider .txt files, excluding 'character_attributes.txt'
    txt_names = [
        n for n in names
        if n.lower().endswith(".txt") and not should_skip_filename(n)
    ]

    if not txt_names:
        raise FileNotFoundError(
            f"No .txt files (excluding character_attributes.txt) found under {src_dir}"
        )

    # Sort primarily by Question_XX index; tie-break alphabetically for stability
    txt_names.sort(key=lambda n: (extract_question_index(n), n.lower()))

    logger.info(f"🖼️ Found {len(txt_names)} image prompt files to merge.")
    for i, n in enumerate(txt_names, start=1):
        logger.info(f"  {i:02d}. {n}")

    # Read & concatenate with exactly one newline between snippets
    merged_chunks: List[str] = []
    for fname in txt_names:
        rel_path = f"{src_dir}/{fname}"
        logger.info(f"📥 Reading: {rel_path}")
        content = read_supabase_file(rel_path, binary=False)
        content = (content or "").rstrip()
        if content:
            merged_chunks.append(content)
        else:
            logger.warning(f"⚠️ Empty content in {rel_path}; skipping.")

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
        "files_merged": len(merged_chunks),
        "ignored_files": [n for n in names if should_skip_filename(n)],
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
