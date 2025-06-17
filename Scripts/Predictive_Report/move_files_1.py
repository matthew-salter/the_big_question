import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER")

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
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={src_prefix}"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code != 200:
        logger.warning(f"❌ Failed to list files in: {src_prefix}")
        return

    files = [item for item in resp.json() if not item["name"].endswith(".keep")]
    if not files:
        logger.info(f"📬 No files to move in: {src_prefix}")
        return

    logger.info(f"📦 Found {len(files)} files in: {src_prefix}")
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
        # ✅ Ensure root prefix
        if not folder.startswith(SUPABASE_ROOT_FOLDER):
            folder = f"{SUPABASE_ROOT_FOLDER}/{folder}"
        keep_file = f"{folder.rstrip('/')}/.keep"
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{keep_file}"

        logger.info(f"🧹 Attempting delete of .keep: {keep_file}")
        resp = requests.delete(url, headers=headers)

        if resp.status_code in (200, 204):
            logger.info(f"🧹 Deleted .keep file: {keep_file}")
        elif resp.status_code == 404:
            logger.debug(f"📬 No .keep file to delete in: {keep_file}")
        else:
            logger.warning(f"⚠️ Failed to delete .keep file: {keep_file} | Status: {resp.status_code}")

def run_prompt(data: dict) -> dict:
    run_ids = {
        "client_context": data["client_context_run_id"],
        "combine": data["combine_run_id"],
        "csv_content": data["csv_content_run_id"],
        "format_combine": data["format_combine_run_id"],
        "format_image_prompts": data["format_image_prompts_run_id"],
        "prompt_1_thinking": data["prompt_1_thinking_run_id"],
        "change_effect_maths": data["change_effect_maths_run_id"],
        "prompt_2_section_assets": data["prompt_2_section_assets_run_id"],
        "prompt_3_report_assets": data["prompt_3_report_assets_run_id"],
        "prompts_4_tables": data["prompts_4_tables_run_id"],
        "report_image_prompts": data["report_image_prompts_run_id"],
        "section_image_prompts": data["section_image_prompts_run_id"]
    }

    folder_paths = [f.strip() for f in data["expected_folders"].split(",")]
    target_map = {p.split("/")[-1]: p for p in folder_paths}

    # ✅ Add root folder prefix if missing
    for key in target_map:
        if not target_map[key].startswith(SUPABASE_ROOT_FOLDER):
            target_map[key] = f"{SUPABASE_ROOT_FOLDER}/{target_map[key]}"
    skipped_files = []

    file_jobs = [
        ("Client_Context", run_ids["client_context"], "Outputs", "client_context", "txt"),
        ("Combine", run_ids["combine"], "Outputs", "combine", "txt"),
        ("csv_Content", run_ids["csv_content"], "InDesign_Import_csv", "csv_content", "csv"),
        ("Format_Combine", run_ids["format_combine"], "Report_Content_txt", "format_combine", "txt"),
        ("Format_Image_Prompts", run_ids["format_image_prompts"], "Image_Prompts", "format_image_prompts", "txt"),
        ("Prompt_1_Thinking", run_ids["prompt_1_thinking"], "Outputs", "prompt_1_thinking", "txt"),
        ("Change_Effect_Maths", run_ids["change_effect_maths"], "Outputs", "change_effect_maths", "txt"),
        ("Prompt_2_Section_Assets", run_ids["prompt_2_section_assets"], "Outputs", "prompt_2_section_assets", "txt"),
        ("Prompt_3_Report_Assets", run_ids["prompt_3_report_assets"], "Outputs", "prompt_3_report_assets", "txt"),
        ("Prompt_4_Tables", run_ids["prompts_4_tables"], "Outputs", "prompts_4_tables", "txt"),
        ("Report_Image_Prompts", run_ids["report_image_prompts"], "Outputs", "report_image_prompts", "txt"),
        ("Section_Image_Prompts", run_ids["section_image_prompts"], "Outputs", "section_image_prompts", "txt"),
    ]

    for folder, run_id, dest_key, prefix, ext in file_jobs:
        from_path = f"{SUPABASE_ROOT_FOLDER}/Predictive_Report/Ai_Responses/{folder}/{run_id}.{ext}"
        to_folder = target_map.get(dest_key)
        if to_folder:
            to_path = f"{to_folder}/{prefix}_{run_id}_.{ext}"
            move_supabase_file(from_path, to_path, skipped_files)

    move_folder_contents(f"{SUPABASE_ROOT_FOLDER}/Predictive_Report/Logos", target_map.get("Logos", ""), skipped_files)
    move_folder_contents(f"{SUPABASE_ROOT_FOLDER}/Predictive_Report/Question_Context", target_map.get("Question_Context", ""), skipped_files)
    move_folder_contents(f"{SUPABASE_ROOT_FOLDER}/Predictive_Report/Ai_Responses/Report_and_Section_Tables", target_map.get("Report_Tables", target_map.get("Report_and_Section_Tables", "")), skipped_files)

    copy_supabase_file(f"{SUPABASE_ROOT_FOLDER}/General_Files/Panelitix_Logo.png",f"{target_map.get('Logos', '')}/Panelitix_Logo.png",skipped_files)

    delete_keep_files(folder_paths)

    return {
        "status": "started",
        "message": "File move operations triggered. You can verify moved files via 2nd webhook.",
        "expected_folders": folder_paths,
        "skipped_files": skipped_files
    }
