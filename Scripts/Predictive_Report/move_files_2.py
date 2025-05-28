import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

FOLDER_PATHS = [
    "The_Big_Question/Predictive_Report/Logos",
    "The_Big_Question/Predictive_Report/Question_Context",
    "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
]

def list_supabase_files(prefix):
    headers = get_supabase_headers()
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={prefix}/"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code != 200:
        logger.warning(f"❌ Failed to list files in: {prefix}")
        return []
    return [item["name"].split("/")[-1] for item in resp.json() if not item["name"].endswith(".keep")]

def run_prompt(_: dict) -> dict:
    result = {}
    for folder in FOLDER_PATHS:
        result[folder] = list_supabase_files(folder)
    return {
        "status": "completed",
        "message": "File listing complete.",
        "files_found": result
    }

