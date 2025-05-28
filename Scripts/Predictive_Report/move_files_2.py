import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"


def list_files_in_folder(folder_path):
    headers = get_supabase_headers()
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={folder_path}/"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code == 200:
        return [item["name"].split("/")[-1] for item in resp.json() if item["name"].split("/")[-1] != ".keep"]
    return []


def find_matching_write_folders(expected_folders):
    subfolder_keywords = ["Question_Context", "Logos", "Report_and_Section_Tables"]
    matches = {key: None for key in subfolder_keywords}

    for folder in expected_folders:
        for keyword in subfolder_keywords:
            if folder.endswith(f"/{keyword}"):
                matches[keyword] = folder

    found_folders = {}
    headers = get_supabase_headers()
    for keyword, path in matches.items():
        if not path:
            found_folders[keyword] = None
            continue

        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={path}/"
        resp = requests.get(list_url, headers=headers)
        if resp.status_code == 200 and len(resp.json()) > 0:
            found_folders[keyword] = path
        else:
            found_folders[keyword] = None

    return found_folders


def run_prompt(data: dict) -> dict:
    source_folders = {
        "Report_and_Section_Tables": "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables",
        "Logos": "The_Big_Question/Predictive_Report/Logos",
        "Question_Context": "The_Big_Question/Predictive_Report/Question_Context"
    }

    source_results = {}
    for key, path in source_folders.items():
        files = list_files_in_folder(path)
        source_results[f"Files Found {path.replace('/', ' ')}"] = files if files else ["(empty)"]

    expected_folders = [f.strip() for f in data.get("expected_folders", "").split(",") if f.strip()]
    write_folders = find_matching_write_folders(expected_folders)

    return {
        **source_results,
        "Write Folders Found": write_folders,
        "status": "completed",
        "message": "File listing complete."
    }
