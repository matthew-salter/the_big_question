import os
from datetime import datetime
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def normalise_path_segment(segment):
    return segment.strip().replace(" ", "_").title()

def uppercase_path_segment(segment):
    return segment.strip().replace(" ", "_").upper()

def create_folder(path):
    """
    Supabase uses object keys to simulate folders.
    To create a folder, upload a zero-byte file ending in '/'.
    """
    if not SUPABASE_URL:
        raise EnvironmentError("SUPABASE_URL is not configured.")

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}.keep"
    headers = get_supabase_headers()
    headers["Content-Type"] = "text/plain"

    # Check if folder already exists by attempting HEAD request
    check_url = f"{SUPABASE_URL}/storage/v1/object/info/{SUPABASE_BUCKET}/{path}.keep"
    check_resp = requests.get(check_url, headers=headers)
    if check_resp.status_code == 200:
        logger.info(f"📂 Folder already exists: {path}")
        return

    response = requests.put(url, headers=headers, data=b"")
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to create folder: {path} | {response.status_code} - {response.text}")
    logger.info(f"✅ Created folder: {path}")

def run_prompt(data: dict) -> dict:
    client_raw = data["client"]
    target_variable_raw = data["target_variable"]
    commodity_raw = data["commodity"]
    region_raw = data["region"]
    time_range_raw = data["time_range"]
    today_date_raw = data["today_date"]

    # Format folder names
    client = normalise_path_segment(client_raw)
    target_variable = uppercase_path_segment(target_variable_raw)
    date_stamp = today_date_raw.replace("/", "-").replace(" ", "_").replace(":", "")
    full_context = uppercase_path_segment(f"{target_variable_raw}_of_{commodity_raw}_in_the_{region_raw}_over_the_next_{time_range_raw}")

    # Construct paths
    base_path = f"The_Big_Question/Predictive_Report/Completed_Reports/{client}"
    dated_path = f"{base_path}/{target_variable}_{date_stamp}"
    context_path = f"{dated_path}/{full_context}"

    subfolders = [
        "Image_Prompts",
        "InDesign_Import_csv",
        "Logos",
        "Outputs",
        "Question_Context",
        "Report_Content_txt"
    ]

    # Create folders sequentially
    for path in [base_path, dated_path, context_path]:
        create_folder(path)

    for sub in subfolders:
        create_folder(f"{context_path}/{sub}")

    return {"status": "success", "message": "Folders created successfully."}
