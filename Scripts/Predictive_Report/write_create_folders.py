import os
import uuid
import threading
import requests
from datetime import datetime
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def normalise_path_segment(segment):
    return segment.strip().replace(" ", "_").title()

def uppercase_path_segment(segment):
    return segment.strip().replace(" ", "_").upper()

def create_folder(path):
    """Create a folder by uploading a .keep file inside it."""
    keep_file_path = f"{path}/.keep"
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{keep_file_path}"
    headers = get_supabase_headers()
    headers["Content-Type"] = "text/plain"

    try:
        # Check if it already exists
        check_url = f"{SUPABASE_URL}/storage/v1/object/info/{SUPABASE_BUCKET}/{keep_file_path}"
        check_resp = requests.get(check_url, headers=headers, timeout=5)
        if check_resp.status_code == 200:
            logger.info(f"📂 Folder already exists: {path}")
            return

        # Attempt upload
        response = requests.put(url, headers=headers, data=b"", timeout=10)
        if response.status_code not in (200, 201):
            logger.warning(f"⚠️ Folder creation failed: {path} ({response.status_code}) - {response.text}")
        else:
            logger.info(f"✅ Created folder: {path}")
    except Exception as e:
        logger.error(f"❌ Exception creating folder {path}: {e}")

def build_expected_paths(data):
    client_raw = data["client"]
    target_variable_raw = data["target_variable"]
    commodity_raw = data["commodity"]
    region_raw = data["region"]
    time_range_raw = data["time_range"]
    today_date_raw = data["today_date"]

    client = normalise_path_segment(client_raw)
    target_variable = uppercase_path_segment(target_variable_raw)
    date_stamp = today_date_raw.replace("/", "-").replace(" ", "_").replace(":", "")
    full_context = uppercase_path_segment(f"{target_variable_raw}_of_{commodity_raw}_in_the_{region_raw}_over_the_next_{time_range_raw}")

    base_path = f"The_Big_Question/Predictive_Report/Completed_Reports/{client}"
    dated_path = f"{base_path}/{target_variable}_{date_stamp}"
    context_path = f"{dated_path}/{full_context}"

    subfolders = [
        "Image_Prompts",
        "InDesign_Import_csv",
        "Logos",
        "Outputs",
        "Question_Context",
        "Report_Content_txt",
        "Report_and_Section_Tables"
    ]

    expected_paths = [base_path, dated_path, context_path]
    expected_paths += [f"{context_path}/{folder}" for folder in subfolders]
    return expected_paths

def background_create_folders(paths):
    for path in paths:
        create_folder(path)

def run_prompt(data: dict) -> dict:
    run_id = str(uuid.uuid4())
    expected_paths = build_expected_paths(data)

    # Launch background folder creation
    thread = threading.Thread(target=background_create_folders, args=(expected_paths,))
    thread.start()

    logger.info(f"🚀 Kicked off background folder creation for run_id: {run_id}")
    return {
        "status": "processing",
        "run_id": run_id,
        "expected_paths": expected_paths
    }
