# Scripts/Explainer_Report/merge_questions.py

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
INDIVIDUAL_SUBDIR = "Individal_Question_Outputs"   # (keep spelling as used)
MERGED_SUBDIR = "Merged_Question_Outputs"

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def list_supabase_folder(prefix: str) -> List[Dict[str, Any]]:
    """
    List objects in a Supabase Storage folder using the official list endpoint:
      POST /storage/v1/object/list/{bucket}
    Body: {"prefix": "<path>/", "limit": 1000, "offset": 0, "sortBy":{"column":"name","order":"asc"}}
    Returns a list of objects with 'name' keys (filenames within the folder).
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
    items = resp.json() or []
    # Each item typically: {"name":"01_question.txt","id": "...", "updated_at": "...", "metadata": {...}}
    return items

def extract_index(filename: str) -> Tuple[int, str]:
    """
    Extract leading numeric index from filenames like '01_...txt'.
    Returns (index, filename) where index defaults to a large number if not found,
    so non-conforming files sort to the end.
    """
    m = re.match(r"^(\d+)[_\-]", filename)
    if m:
        try:
            return int(m.group(1)), filename
        except ValueError:
            pass
    return (10**9, filename)  # push unexpected names to end

def normalize_name(value: str) -> str:
    """
    Turn names/condition into clean filename segments.
    """
    value = value.strip()
    value = re.sub(r"[^\w\s\-]", "", value)
    value = re.sub(r"\s+", "_", value)
    return value

def normalize_date_for_filename(value: str) -> str:
    """
    Convert date like '08/18/25 04:42PM' to '08-18-25_0442PM' (keep AM/PM).
    Works pass-through if value is already in a nice format.
    """
    v = value.strip()
    v = v.replace("/", "-").replace(" ", "_").replace(":", "")
    return v

# -------------------------------------------------------------------
# Core
# -------------------------------------------------------------------

def merge_questions(run_id: str, first_name: str, sur_name: str,
                    condition: str, todays_date: str) -> Dict[str, Any]:
    """
    Merge all individual question .txt files (JSON snippets) for a run_id
    into one .txt file, preserving numeric order by filename prefix.
    """
    # Resolve folders
    indiv_dir = f"{PARENT_DIR}/{run_id}/{INDIVIDUAL_SUBDIR}"
    merged_dir = f"{PARENT_DIR}/{run_id}/{MERGED_SUBDIR}"

    # List files in the individual outputs folder
    items = list_supabase_folder(indiv_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]

    # Filter to .txt only
    txt_names = [n for n in names if n.lower().endswith(".txt")]
    # Sort by leading index
    txt_names.sort(key=lambda n: extract_index(n)[0])

    if not txt_names:
        raise FileNotFoundError(f"No .txt files found under {indiv_dir}")

    logger.info(f"🧾 Found {len(txt_names)} question files to merge.")

    # Read and concatenate
    merged_chunks: List[str] = []
    for fname in txt_names:
        rel_path = f"{indiv_dir}/{fname}"  # relative to SUPABASE_ROOT_FOLDER inside read_supabase_file
        logger.info(f"📥 Reading: {rel_path}")
        content = read_supabase_file(rel_path, binary=False)
        content = content.strip()
        if content:
            merged_chunks.append(content)
        else:
            logger.warning(f"⚠️ Empty content in {rel_path}, including as blank section.")

    merged_text = "\n\n".join(merged_chunks) + "\n"

    # Build output filename
    first = normalize_name(first_name or "Unknown")
    last = normalize_name(sur_name or "User")
    cond = normalize_name(condition or "Condition")
    date_seg = normalize_date_for_filename(todays_date or "")

    out_name = f"{first}_{last}_{cond}_Merged_Question_Jsons_{date_seg}.txt"
    out_path = f"{merged_dir}/{out_name}"

    # Write to Supabase (text/plain)
    logger.info(f"📤 Writing merged file: {out_path}")
    write_supabase_file(out_path, merged_text, content_type="text/plain; charset=utf-8")

    return {
        "status": "ok",
        "run_id": run_id,
        "files_merged": len(txt_names),
        "output_path": out_path,
    }

# -------------------------------------------------------------------
# Public entrypoint for main.py
# -------------------------------------------------------------------

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected payload from Zapier:
      {
        "run_id": "...",
        "first_name": "Karen",
        "sur_name": "Chapman",
        "condition": "Severe Osteoporosis",
        "todays_date": "08/07/25 04:44PM"
      }
    Returns a small JSON summary including the merged file path.
    """
    run_id = data.get("run_id")
    if not run_id:
        raise ValueError("run_id is required")

    first_name = data.get("first_name", "")
    sur_name = data.get("sur_name", "")
    condition = data.get("condition", "")
    todays_date = data.get("todays_date", "")

    logger.info(f"🧩 merge_questions.run_prompt: run_id={run_id}, first_name={first_name}, sur_name={sur_name}, condition={condition}, todays_date={todays_date}")

    result = merge_questions(
        run_id=run_id,
        first_name=first_name,
        sur_name=sur_name,
        condition=condition,
        todays_date=todays_date,
    )
    return result
