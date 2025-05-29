import os
import requests
from logger import logger
from Engine.Files.auth import get_supabase_headers

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

SOURCE_FOLDERS = [
    "The_Big_Question/Predictive_Report/Logos",
    "The_Big_Question/Predictive_Report/Question_Context",
    "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
]

TARGET_SUFFIXES = [
    "/Report_and_Section_Tables/",
    "/Logos/",
    "/Question_Context/"
]

def list_files_in_folder(folder_path: str):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    if not folder_path.endswith("/"):
        folder_path += "/"

    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"
    payload = {"prefix": folder_path, "limit": 1000}

    try:
        logger.info(f"📂 Listing files in folder: {folder_path}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        files = response.json()
        file_names = [f["name"].split("/")[-1] for f in files if not f["name"].endswith("/")]
        logger.info(f"🧾 Files found: {file_names}")
        return file_names

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to list files in {folder_path}: {e}")
        return []

def find_target_folders(expected_folders_str: str):
    logger.info("🔍 Starting Stage 2: Write target folder validation")
    target_lookup = {}
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"

    all_expected = expected_folders_str.split(",")
    relevant_targets = [folder for folder in all_expected if any(folder.endswith(suffix) for suffix in TARGET_SUFFIXES)]

    for folder in relevant_targets:
        # List objects in the folder to confirm existence
        url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
        payload = {"prefix": folder, "limit": 1}

        try:
            logger.info(f"🔎 Checking folder: {folder}")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            files = response.json()

            if files and any(not f["name"].endswith("/") for f in files):
                logger.info(f"✅ Folder exists: {folder}")
                target_lookup[folder] = "found"
            else:
                logger.info(f"❌ Folder empty or not found: {folder}")
                target_lookup[folder] = "not found"

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Folder lookup failed: {folder} → {e}")
            target_lookup[folder] = "not found"

    return target_lookup

def run_prompt(payload: dict) -> dict:
    logger.info("🚀 Starting Stage 1: Source folder file lookup")
    stage_1_results = {}
    for folder in SOURCE_FOLDERS:
        files = list_files_in_folder(folder)
        stage_1_results[folder] = files

    logger.info("📦 Completed Stage 1")

    logger.info("🚀 Starting Stage 2: Target folder validation")
    expected_folders_str = payload.get("expected_folders", "")
    stage_2_results = find_target_folders(expected_folders_str)

    logger.info("📦 Completed Stage 2")

    return {
        "source_folder_files": stage_1_results,
        "target_folder_lookup": stage_2_results
    }
