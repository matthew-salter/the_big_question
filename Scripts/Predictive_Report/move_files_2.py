# Scripts/Predictive_Report/move_files_2.py

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

def list_files_in_folder(folder_path: str):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    # Ensure trailing slash
    if not folder_path.endswith("/"):
        folder_path += "/"

    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    headers = get_supabase_headers()
    params = {"prefix": folder_path, "limit": 1000}

    try:
        logger.info(f"📂 Listing files in folder: {folder_path}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        files = response.json()

        file_names = [file['name'].split('/')[-1] for file in files if not file['name'].endswith('/')]
        logger.info(f"🧾 Files found: {file_names}")
        return file_names

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to list files in {folder_path}: {e}")
        return []

def run_prompt(_: dict) -> dict:
    logger.info("🚀 Starting Stage 1: Source folder file lookup")
    results = {}

    for folder in SOURCE_FOLDERS:
        files = list_files_in_folder(folder)
        results[folder] = files

    logger.info("✅ File lookup complete")
    return results
