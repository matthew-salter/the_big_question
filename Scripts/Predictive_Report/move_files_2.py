import os
import requests
from logger import logger
from Engine.Files.auth import get_supabase_headers
from Engine.Files.read_copy_supabase_file import read_copy_supabase_file
from Engine.Files.write_copy_supabase_file import write_copy_supabase_file

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def delete_supabase_file(path: str):
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()
    response = requests.delete(url, headers=headers)
    response.raise_for_status()

def run_prompt(payload):
    # --- Stage 1: Read source folders and list files ---
    source_folders = [
        "The_Big_Question/Predictive_Report/Logos",
        "The_Big_Question/Predictive_Report/Question_Context",
        "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
    ]

    stage_1_results = {}
    for folder in source_folders:
        try:
            url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={folder}/"
            headers = get_supabase_headers()
            res = requests.get(url, headers=headers)
            res.raise_for_status()
            files = [item["name"].split("/")[-1] for item in res.json() if item["name"] != f"{folder}/"]
            stage_1_results[folder] = files
        except Exception as e:
            logger.error(f"Error reading folder {folder}: {e}")
            stage_1_results[folder] = []

    # --- Stage 2: Validate write target folders ---
    expected_paths = payload.get("expected_folders", "").split(",")
    suffixes = ["Logos", "Question_Context", "Report_and_Section_Tables"]
    stage_2_results = {}

    for suffix in suffixes:
        matching = [p for p in expected_paths if p.endswith(f"/{suffix}") or p.endswith(f"/{suffix}/")]
        if not matching:
            stage_2_results[suffix] = "not found"
            continue

        folder_path = matching[0].rstrip("/")
        try:
            url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={folder_path}/"
            headers = get_supabase_headers()
            res = requests.get(url, headers=headers)
            res.raise_for_status()
            found = any(item["name"].endswith(".keep") for item in res.json())
            stage_2_results[folder_path] = "found" if found else "not found"
        except Exception as e:
            logger.error(f"Error reading target folder {folder_path}: {e}")
            stage_2_results[folder_path] = "not found"

    # --- Stage 3: Move files from source to target ---
    logger.info("🚀 Starting Stage 3: Moving files from source to target")

    for source_folder, files in stage_1_results.items():
        suffix = source_folder.split("/")[-1]
        if suffix not in suffixes:
            logger.warning(f"⚠️ No suffix match for source folder: {source_folder}")
            continue

        target_folder = None
        for target_path in stage_2_results:
            if target_path.endswith(f"/{suffix}") and stage_2_results[target_path] == "found":
                target_folder = target_path
                break

        if not target_folder:
            logger.warning(f"⚠️ No valid target folder for: {source_folder}")
            continue

        for fname in files:
            if fname == ".emptyFolderPlaceholder":
                continue

            source_path = f"{source_folder}/{fname}"
            dest_path = f"{target_folder}/{fname}"

            try:
                content = read_supabase_file(source_path, binary=True)
                write_supabase_file(dest_path, content)
                delete_supabase_file(source_path)
                logger.info(f"✅ Moved {source_path} → {dest_path}")
            except Exception as e:
                logger.error(f"❌ Failed to move {source_path} → {dest_path}: {e}")

    return {
        "source_folder_files": stage_1_results,
        "target_folder_lookup": stage_2_results
    }
