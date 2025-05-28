import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def move_supabase_file(from_path, to_path, skipped_files):
    headers = get_supabase_headers()
    get_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    get_resp = requests.get(get_url, headers=headers)
    if get_resp.status_code != 200:
        logger.warning(f"❌ Failed to fetch {from_path}")
        skipped_files.append(from_path)
        return

    put_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{to_path}"
    put_resp = requests.put(put_url, headers=headers, data=get_resp.content)
    if put_resp.status_code not in (200, 201):
        logger.warning(f"❌ Failed to write {to_path}")
        skipped_files.append(from_path)
        return

    logger.info(f"✅ Moved file: {from_path} → {to_path}")
    delete_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    requests.delete(delete_url, headers=headers)

def move_folder_contents(src_prefix, dst_prefix, skipped_files):
    if not dst_prefix:
        logger.warning(f"⚠️ No destination provided for source: {src_prefix}")
        return
    headers = get_supabase_headers()
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={src_prefix}/"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code != 200:
        logger.warning(f"❌ Failed to list files in: {src_prefix}")
        return

    files = [item for item in resp.json() if not item['name'].endswith("/.keep") and not item['name'].endswith("/")]
    if not files:
        logger.info(f"📂 No files to move in: {src_prefix}")
        return

    for item in files:
        filename = item["name"].split("/")[-1]
        from_path = item["name"]
        to_path = f"{dst_prefix}/{filename}"
        move_supabase_file(from_path, to_path, skipped_files)

def copy_supabase_file(from_path, to_path, skipped_files):
    headers = get_supabase_headers()
    get_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    get_resp = requests.get(get_url, headers=headers)
    if get_resp.status_code != 200:
        logger.warning(f"❌ Failed to copy from {from_path}")
        skipped_files.append(from_path)
        return

    put_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{to_path}"
    put_resp = requests.put(put_url, headers=headers, data=get_resp.content)
    if put_resp.status_code not in (200, 201):
        logger.warning(f"❌ Failed to copy to {to_path}")
        skipped_files.append(from_path)
        return

    logger.info(f"✅ Copied file: {from_path} → {to_path}")

def delete_keep_files(folder_paths):
    headers = get_supabase_headers()
    for folder in folder_paths:
        keep_file = f"{folder}/.keep"
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{keep_file}"
        resp = requests.delete(url, headers=headers)
        if resp.status_code in (200, 204):
            logger.info(f"🪚 Deleted .keep file: {keep_file}")
        elif resp.status_code == 404:
            logger.debug(f"📬 No .keep file to delete in: {keep_file}")
        else:
            logger.warning(f"⚠️ Failed to delete .keep file: {keep_file} | Status: {resp.status_code}")

def run_prompt(data: dict) -> dict:
    folder_paths = [f.strip() for f in data["expected_folders"].split(",")]
    target_map = {p.split("/")[-1]: p for p in folder_paths}
    skipped_files = []

    # Move from source directories to corresponding mapped folders
    move_folder_contents("The_Big_Question/Predictive_Report/Logos", target_map.get("Logos", ""), skipped_files)
    move_folder_contents("The_Big_Question/Predictive_Report/Question_Context", target_map.get("Question_Context", ""), skipped_files)
    move_folder_contents("The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables", target_map.get("Report_Tables", ""), skipped_files)

    # Always copy Panelitix logo into the Logos folder
    copy_supabase_file("The_Big_Question/General_Files/Panelitix_Logo.png", f"{target_map.get('Logos', '')}/Panelitix_Logo.png", skipped_files)

    # Clean up any .keep files if present
    delete_keep_files(folder_paths)

    return {
        "status": "started",
        "message": "File move operations triggered. You can verify moved files via 2nd webhook.",
        "expected_folders": folder_paths,
        "skipped_files": skipped_files
    }
