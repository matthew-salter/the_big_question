import os
import re
import requests
from logger import logger
from collections import defaultdict
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

    # Format Stage 1 results for Zapier as nested dict
    source_folder_files = {}
    for folder, files in stage_1_results.items():
        label = f"Source Folder {folder.replace('/', ' ')}"
        file_dict = {str(i + 1): file for i, file in enumerate(files)}
        source_folder_files[label] = file_dict

    # Format Stage 2 results for Zapier as nested dict
    target_folder_lookup = {}
    for folder, status in stage_2_results.items():
        label = folder.replace("/", " ")
        target_folder_lookup[label] = {"1": status}

    return {
        "source_folder_files": source_folder_files,
        "target_folder_lookup": target_folder_lookup
    }


def copy_and_delete_files(stage_1_results: dict, expected_folders_str: str):
    logger.info("🚀 Starting Stage 3: File copy and cleanup")
    headers = get_supabase_headers()

    expected_folders = expected_folders_str.split(",")
    suffix_map = defaultdict(list)

    for folder in expected_folders:
        for suffix in TARGET_SUFFIXES:
            if folder.endswith(suffix):
                suffix_map[suffix].append(folder)

    logger.info(f"🔁 Suffix map for Stage 3: {dict(suffix_map)}")  # ← HERE

    # Step 2: Process files from source folders
    for source_folder, files in stage_1_results.items():
        for file_name in files:
            if file_name == ".emptyFolderPlaceholder":
                continue  # skip placeholder

            suffix = "/" + source_folder.split("/")[-1] + "/"
            target_folders = suffix_map.get(suffix, [])
            if not target_folders:
                logger.warning(f"⚠️ No target folder found for source {source_folder}")
                continue

            # Use the *first* matching folder (or enhance to handle all if needed)
            target_folder = target_folders[0]

            if not target_folder:
                logger.warning(f"⚠️ No target folder found for source {source_folder}")
                continue

            source_path = f"{source_folder}/{file_name}"
            target_path = f"{target_folder}/{file_name}"

            # Step 3: Download file
            download_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}"
            try:
                logger.info(f"⬇️ Downloading: {source_path}")
                file_response = requests.get(download_url, headers=headers)
                file_response.raise_for_status()
                file_bytes = file_response.content
            except requests.RequestException as e:
                logger.error(f"❌ Failed to download {source_path}: {e}")
                continue

            # Step 4: Upload to target
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{target_path}"
            try:
                logger.info(f"⬆️ Uploading: {target_path}")
                upload_headers = headers.copy()
                upload_headers["Content-Type"] = "application/octet-stream"
                upload_response = requests.post(upload_url, headers=upload_headers, data=file_bytes)
                upload_response.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"❌ Failed to upload to {target_path}: {e}")
                continue

            # Step 5: Delete original
            delete_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{source_path}"
            try:
                logger.info(f"🗑️ Deleting: {source_path}")
                delete_response = requests.delete(delete_url, headers=headers)
                delete_response.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"❌ Failed to delete {source_path}: {e}")

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

    logger.info("🚀 Starting Stage 3")
    copy_and_delete_files(stage_1_results, expected_folders_str)
    logger.info("📦 Completed Stage 3")

    # --- Stage 1 Output (unchanged)
    source_folder_files = {}
    for folder, files in stage_1_results.items():
        readable_label = f"Source Folder {folder.replace('/', ' ')}"
        source_folder_files[readable_label] = [file for file in files]

    # --- Final Output Dict (flattened)
    output = {
        "source_folder_files": source_folder_files
    }

    # --- Stage 2 Output: flattened keys like "target_folder__..."
    for folder, status in stage_2_results.items():
        flat_key = f"target_folder__{folder.replace('/', '_')}"
        output[flat_key] = status  # e.g., "found" or "not found"

    return output
