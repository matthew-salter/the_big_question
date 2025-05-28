import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def list_files_in_folder(folder: str) -> list:
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"
    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    resp = requests.post(url, headers=headers, json={"prefix": f"{folder}/"})

    if resp.status_code != 200:
        logger.warning(f"❌ Failed to list files in: {folder}")
        return []

    return [
        os.path.basename(item["name"])
        for item in resp.json()
        if not item["name"].endswith(".keep")
    ]

def run_prompt(_: dict) -> dict:
    folders_to_check = [
        "The_Big_Question/Predictive_Report/Logos",
        "The_Big_Question/Predictive_Report/Question_Context",
        "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables",
    ]

    results = {}
    for folder in folders_to_check:
        files = list_files_in_folder(folder)
        key = folder.replace("/", " ")
        results[key] = files or [f"No files found in {folder}"]

    return {
        "status": "completed",
        "message": "File listing complete.",
        "files_found": results
    }
