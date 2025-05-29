import os
import re
import requests
from collections import defaultdict
from logger import logger
from Engine.Files.auth import get_supabase_headers

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

# === PART 1: Structured file moves (from move_files_1.py) ===
def structured_file_moves(payload: dict):
    logger.info("📁 Starting PART 1: Structured file moves")
    files_to_move = payload.get("files_to_move", [])
    headers = get_supabase_headers()

    for entry in files_to_move:
        source_path = entry["from"]
        target_path = entry["to"]

        try:
            logger.info(f"⬇️ Downloading: {source_path}")
            download_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}"
            download_response = requests.get(download_url, headers=headers)
            download_response.raise_for_status()
            file_bytes = download_response.content

            logger.info(f"⬆️ Uploading: {target_path}")
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{target_path}"
            upload_headers = headers.copy()
            upload_headers["Content-Type"] = "application/octet-stream"
            upload_response = requests.post(upload_url, headers=upload_headers, data=file_bytes)
            upload_response.raise_for_status()

            logger.info(f"🗑️ Deleting: {source_path}")
            delete_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}"
            delete_response = requests.delete(delete_url, headers=headers)
            delete_response.raise_for_status()

        except requests.RequestException as e:
            logger.error(f"❌ Error processing {source_path} → {target_path}: {e}")

# === PART 2: Full move_files_2.py logic ===

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
        return [f["name"].split("/")[-1] for f in files if not f["name"].endswith("/")]
    except requests.RequestException as e:
        logger.error(f"❌ Failed to list files in {folder_path}: {e}")
        return []

def find_target_folders(expected_folders_str: str):
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"
    all_expected = expected_folders_str.split(",")
    return {
        folder: "found" if any(not f["name"].endswith("/") for f in requests.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}",
            headers=headers,
            json={"prefix": folder, "limit": 1}
        ).json()) else "not found"
        for folder in all_expected if any(folder.endswith(suffix) for suffix in TARGET_SUFFIXES)
    }

def copy_and_delete_files(stage_1_results: dict, expected_folders_str: str):
    headers = get_supabase_headers()
    expected_folders = expected_folders_str.split(",")
    suffix_map = defaultdict(list)
    for folder in expected_folders:
        for suffix in TARGET_SUFFIXES:
            if folder.endswith(suffix):
                suffix_map[suffix].append(folder)

    for source_folder, files in stage_1_results.items():
        for file_name in files:
            if file_name == ".emptyFolderPlaceholder":
                continue

            suffix = "/" + source_folder.split("/")[-1] + "/"
            target_folders = suffix_map.get(suffix, [])
            if not target_folders:
                continue

            target_folder = target_folders[0]
            source_path = f"{source_folder}/{file_name}"
            target_path = f"{target_folder}/{file_name}"

            try:
                file_bytes = requests.get(f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}", headers=headers).content
                upload_headers = headers.copy()
                upload_headers["Content-Type"] = "application/octet-stream"
                requests.post(f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{target_path}", headers=upload_headers, data=file_bytes).raise_for_status()
                requests.delete(f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}", headers=headers).raise_for_status()
            except requests.RequestException as e:
                logger.error(f"❌ Failed processing file: {source_path} → {e}")

# === PART 3: Cleanup placeholder files ===
def cleanup_empty_folder_placeholders():
    headers = get_supabase_headers()
    folders = SOURCE_FOLDERS
    for folder in folders:
        placeholder_path = f"{folder}/.emptyFolderPlaceholder"
        try:
            delete_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{placeholder_path}"
            delete_response = requests.delete(delete_url, headers=headers)
            if delete_response.status_code == 200:
                logger.info(f"🧹 Removed placeholder: {placeholder_path}")
        except requests.RequestException as e:
            logger.warning(f"⚠️ Could not delete placeholder {placeholder_path}: {e}")

# === Entry point ===
def run_prompt(payload: dict) -> dict:
    structured_file_moves(payload)

    stage_1_results = {folder: list_files_in_folder(folder) for folder in SOURCE_FOLDERS}
    expected_folders_str = payload.get("expected_folders", "")
    find_target_folders(expected_folders_str)  # Stage 2 (no output needed unless logging)
    copy_and_delete_files(stage_1_results, expected_folders_str)

    cleanup_empty_folder_placeholders()

    return {"status": "success"}
