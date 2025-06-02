import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def normalise_path_segment(segment):
    return segment.strip().replace(" ", "_").title()

def uppercase_path_segment(segment):
    return segment.strip().replace(" ", "_").upper()

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
    dated_folder = f"{target_variable}_{date_stamp}"
    context_folder = uppercase_path_segment(f"{commodity_raw}_in_the_{region_raw}_over_the_next_{time_range_raw}")

    base_path = f"The_Big_Question/Predictive_Report/Completed_Reports/{client}"
    context_path = f"{base_path}/{context_folder}"
    dated_path = f"{context_path}/{dated_folder}"

    subfolders = [
        "Image_Prompts",
        "InDesign_Import_csv",
        "Logos",
        "Outputs",
        "Question_Context",
        "Report_Content_txt",
        "Report_and_Section_Tables"
    ]

    expected_paths = [base_path, context_path, dated_path]
    expected_paths += [f"{dated_path}/{folder}" for folder in subfolders]
    return expected_paths

def folder_exists(path: str) -> bool:
    """
    Checks whether a given folder exists in Supabase by confirming the `.keep` marker is present.
    """
    keep_file_path = f"{path}/.keep"
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
    try:
        folder_list = build_expected_paths(data)
    except KeyError as e:
        return {
            "status": "error",
            "message": f"Missing required key in payload: {str(e)}"
        }

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
