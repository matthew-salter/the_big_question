import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

# Folder paths to check
SOURCE_FOLDERS = {
    "Logos": "The_Big_Question/Predictive_Report/Logos",
    "Question_Context": "The_Big_Question/Predictive_Report/Question_Context",
    "Report_and_Section_Tables": "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
}

def list_files_in_folder(folder_path):
    headers = get_supabase_headers()
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={folder_path}/"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code != 200:
        logger.warning(f"❌ Failed to list files in: {folder_path}")
        return []
    files = [item["name"].split("/")[-1] for item in resp.json() if not item["name"].endswith(".keep")]
    return files

def run_prompt(data: dict) -> dict:
    headers = get_supabase_headers()
    expected_folders = [f.strip() for f in data.get("expected_folders", "").split(",") if f.strip()]
    write_folder_map = {folder.split("/")[-1]: folder for folder in expected_folders}

    result = {
        "status": "completed",
        "message": "File listing complete.",
        "files_found": {},
        "write_folders_found": []
    }

    # List files in source folders
    for key, path in SOURCE_FOLDERS.items():
        files = list_files_in_folder(path)
        result["files_found"][key] = files if files else []

    # Confirm which expected write folders exist
    for expected in ["Logos", "Question_Context", "Report_and_Section_Tables"]:
        if expected in write_folder_map:
            result["write_folders_found"].append(expected)

    return result
