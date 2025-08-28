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
INDIVIDUAL_SUBDIR = "Individal_Question_Outputs"   # keep existing spelling
MERGED_SUBDIR = "Merged_Question_Outputs"

AE_BE_PATH = "Prompts/American_to_British/american_to_british.txt"

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

    logger.info(f"📄 Listing Supabase folder: {payload['prefix']}")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    return resp.json() or []

def extract_index(filename: str) -> Tuple[int, str]:
    m = re.match(r"^(\d+)[_\-]", filename)
    if m:
        try:
            return int(m.group(1)), filename
        except ValueError:
            pass
    return (10**9, filename)

def normalize_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^\w\s\-]", "", value)
    value = re.sub(r"\s+", "_", value)
    return value or "Unknown"

def normalize_date_for_filename(value: str) -> str:
    v = (value or "").strip()
    v = v.replace("/", "-").replace(" ", "_").replace(":", "")
    return v or "date"

# ---------------- AE → BE conversion ----------------

_PAIR_RE = re.compile(r'"([^"]+)"\s*:\s*"([^"]+)"')

def load_ae_be_mapping(path: str) -> Dict[str, str]:
    """
    Parse a tolerant '"American": "British"' mapping file.
    Handles duplicates; last one wins.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        logger.warning(f"⚠️ AE→BE mapping not found at {path}; skipping conversion.")
        return {}

    mapping: Dict[str, str] = {}
    for m in _PAIR_RE.finditer(text):
        american = m.group(1)
        british = m.group(2)
        mapping[american] = british
    logger.info(f"🇺🇸→🇬🇧 Loaded {len(mapping)} AE→BE replacements from {path}")
    return mapping

def compile_ae_be_regex(mapping: Dict[str, str]) -> Tuple[re.Pattern, Dict[str, str]]:
    """
    Build a single compiled regex that matches any American term as a whole word.
    Using (?<!\\w) ... (?!\\w) to avoid partial-word hits (e.g., 'program' in 'programmer').
    Sort keys by length desc to favor longer matches when adjacent.
    """
    if not mapping:
        return None, mapping
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)"
    return re.compile(pattern), mapping

def american_to_british(text: str, compiled: Tuple[re.Pattern, Dict[str, str]]) -> str:
    if not compiled or not compiled[0]:
        return text
    pattern, mapping = compiled
    return pattern.sub(lambda m: mapping.get(m.group(1), m.group(1)), text)

# -------------------------------------------------------------------
# Core
# -------------------------------------------------------------------

def merge_questions(run_id: str, first_name: str, sur_name: str,
                    condition: str, todays_date: str) -> Dict[str, Any]:
    """
    Merge all individual question .txt files (JSON snippets) for a given run_id
    into a single .txt file, preserving numeric order, then convert AE→BE.
    """
    # Resolve folders
    indiv_dir = f"{PARENT_DIR}/{run_id}/{INDIVIDUAL_SUBDIR}"
    merged_dir = f"{PARENT_DIR}/{run_id}/{MERGED_SUBDIR}"

    # List files in the individual outputs folder
    items = list_supabase_folder(indiv_dir)
    names = [it["name"] for it in items if isinstance(it, dict) and "name" in it]

    # Only .txt files
    txt_names = [n for n in names if n.lower().endswith(".txt")]

    # Sort by leading index, then by name for stability
    txt_names.sort(key=lambda n: (extract_index(n)[0], n.lower()))

    if not txt_names:
        raise FileNotFoundError(f"No .txt files found under {indiv_dir}")

    logger.info(f"🧾 Found {len(txt_names)} question files to merge.")

    # Read and concatenate with exactly one newline between snippets
    merged_chunks: List[str] = []
    for fname in txt_names:
        rel_path = f"{indiv_dir}/{fname}"
        logger.info(f"📥 Reading: {rel_path}")
        content = read_supabase_file(rel_path, binary=False)
        content = (content or "").rstrip()
        if content:
            merged_chunks.append(content)
        else:
            logger.warning(f"⚠️ Empty content in {rel_path}; skipping empty chunk.")

    merged_text = "\n".join(merged_chunks) + "\n"

    # ---- AE → BE conversion step ----
    mapping = load_ae_be_mapping(AE_BE_PATH)
    compiled = compile_ae_be_regex(mapping)
    merged_text = american_to_british(merged_text, compiled)

    # Build output filename
    first = normalize_name(first_name)
    last = normalize_name(sur_name)
    cond = normalize_name(condition)
    date_seg = normalize_date_for_filename(todays_date)

    out_name = f"{first}_{last}_{cond}_Merged_Question_Jsons_{date_seg}.txt"
    out_path = f"{merged_dir}/{out_name}"

    # Write to Supabase (text/plain)
    logger.info(f"📤 Writing merged file (AE→BE corrected): {out_path}")
    write_supabase_file(out_path, merged_text, content_type="text/plain; charset=utf-8")

    return {
        "status": "ok",
        "run_id": run_id,
        "files_merged": len(txt_names),
        "replacements_loaded": len(mapping),
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
        "first_name": "Karen",
        "sur_name": "Chapman",
        "condition": "Severe Osteoporosis",
        "todays_date": "08/07/25 04:44PM"
      }
    """
    run_id = data.get("run_id")
    if not run_id:
        raise ValueError("run_id is required")

    first_name = data.get("first_name", "")
    sur_name = data.get("sur_name", "")
    condition = data.get("condition", "")
    todays_date = data.get("todays_date", "")

    logger.info(
        f"🧩 merge_questions.run_prompt: run_id={run_id}, "
        f"first_name={first_name}, sur_name={sur_name}, "
        f"condition={condition}, todays_date={todays_date}"
    )

    return merge_questions(
        run_id=run_id,
        first_name=first_name,
        sur_name=sur_name,
        condition=condition,
        todays_date=todays_date,
    )
