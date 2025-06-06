import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER")

def folder_exists(path: str) -> bool:
    """
    Checks whether a given folder exists in Supabase by confirming the `.keep` marker is present.
    """
    full_path = f"{SUPABASE_ROOT_FOLDER}/{path}"
    keep_file_path = f"{full_path}/.keep"
    url = f"{SUPABASE_URL}/storage/v1/object/info/{SUPABASE_BUCKET}/{keep_file_path}"
    headers = get_supabase_headers()

    try:
        logger.info(f"🔍 Checking folder: {path}")
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info(f"✅ Folder exists: {path}")
            return True
        logger.warning(f"❌ Folder does not exist (status {resp.status_code}): {path}")
        return False
    except Exception as e:
        logger.error(f"❌ Exception checking folder {path}: {e}")
        return False

def run_prompt(data: dict) -> dict:
    folder_list_raw = data.get("expected_folders", "")
    folder_list = [f.strip() for f in folder_list_raw.split(",") if f.strip()]

    if not folder_list:
        return {"status": "error", "message": "No expected_folders provided."}

    missing_folders = [path for path in folder_list if not folder_exists(path)]

    if missing_folders:
        return {
            "status": "folder directories do not exist",
            "missing": missing_folders,
            "checked": folder_list
        }

    return {
        "status": "folder directories exist",
        "checked": folder_list
    }
