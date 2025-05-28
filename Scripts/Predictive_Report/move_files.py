import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def move_supabase_file(from_path, to_path):
    headers = get_supabase_headers()

    # Read original file
    get_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    get_resp = requests.get(get_url, headers=headers)
    if get_resp.status_code != 200:
        logger.warning(f"❌ Failed to fetch {from_path}")
        return

    # Upload to destination
    put_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{to_path}"
    put_resp = requests.put(put_url, headers=headers, data=get_resp.content)
    if put_resp.status_code not in (200, 201):
        logger.warning(f"❌ Failed to write {to_path}")
        return

    logger.info(f"✅ Moved file: {from_path} → {to_path}")

    # Delete original
    delete_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    requests.delete(delete_url, headers=headers)

def copy_supabase_file(from_path, to_path):
    headers = get_supabase_headers()
    get_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{from_path}"
    get_resp = requests.get(get_url, headers=headers)
    if get_resp.status_code != 200:
        logger.warning(f"❌ Failed to copy from {from_path}")
        return

    put_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{to_path}"
    put_resp = requests.put(put_url, headers=headers, data=get_resp.content)
    if put_resp.status_code not in (200, 201):
        logger.warning(f"❌ Failed to copy to {to_path}")
        return

    logger.info(f"✅ Copied file: {from_path} → {to_path}")

def delete_keep_files(folder_paths):
    headers = get_supabase_headers()
    for folder in folder_paths:
        keep_file = f"{folder}/.keep"
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{keep_file}"
        delete_resp = requests.delete(url, headers=headers)
        if delete_resp.status_code in (200, 204):
            logger.info(f"🧹 Deleted .keep file: {keep_file}")
        elif delete_resp.status_code == 404:
            logger.debug(f"📭 No .keep file to delete in: {keep_file}")
        else:
            logger.warning(f"⚠️ Failed to delete .keep file: {keep_file} | Status: {delete_resp.status_code}")

def run_prompt(data: dict) -> dict:
    run_ids = {
        "client_context": data["client_context_run_id"],
        "combine": data["combine_run_id"],
        "csv_content": data["csv_content_run_id"],
        "format_combine": data["format_combine_run_id"],
        "format_image_prompts": data["format_image_prompts_run_id"],
        "prompt_1_thinking": data["prompt_1_thinking_run_id"],
        "prompt_2_section_assets": data["prompt_2_section_assets_run_id"],
        "prompt_3_report_assets": data["prompt_3_report_assets_run_id"],
        "prompts_4_tables": data["prompts_4_tables_run_id"],
        "report_image_prompts": data["report_image_prompts_run_id"],
        "section_image_prompts": data["section_image_prompts_run_id"]
    }

    folder_paths = [f.strip() for f in data["expected_folders"].split(",")]
    target_map = {p.split("/")[-1]: p for p in folder_paths}

    # Standard .txt/.csv renames
    file_jobs = [
        ("Client_Context", run_ids["client_context"], "Outputs", "client_context", "txt"),
        ("Combine", run_ids["combine"], "Outputs", "combine", "txt"),
        ("csv_Content", run_ids["csv_content"], "InDesign_Import_csv", "csv_content", "csv"),
        ("Format_Combine", run_ids["format_combine"], "Report_Content_txt", "format_combine", "txt"),
        ("Format_Image_Prompts", run_ids["format_image_prompts"], "Image_Prompts", "format_image_prompts", "txt"),
        ("Prompt_1_Thinking", run_ids["prompt_1_thinking"], "Outputs", "prompt_1_thinking", "txt"),
        ("Prompt_2_Section_Assets", run_ids["prompt_2_section_assets"], "Outputs", "prompt_2_section_assets", "txt"),
        ("Prompt_3_Report_Assets", run_ids["prompt_3_report_assets"], "Outputs", "prompt_3_report_assets", "txt"),
        ("Prompt_4_Tables", run_ids["prompts_4_tables"], "Outputs", "prompts_4_tables", "txt"),
        ("Report_Image_Prompts", run_ids["report_image_prompts"], "Outputs", "report_image_prompts", "txt"),
        ("Section_Image_Prompts", run_ids["section_image_prompts"], "Outputs", "section_image_prompts", "txt"),
    ]

    for folder, run_id, dest_key, prefix, ext in file_jobs:
        if ext == "csv":
            from_path = f"The_Big_Question/Predictive_Report/Ai_Responses/{folder}/{run_id}.csv"
        else:
            from_path = f"The_Big_Question/Predictive_Report/Ai_Responses/{folder}/{run_id}.txt"

        to_folder = target_map[dest_key]
        to_path = f"{to_folder}/{prefix}_{run_id}_.{ext}"
        move_supabase_file(from_path, to_path)

    # Report_Tables — move all files
    report_tables_src = "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
    report_tables_dst = target_map.get("Report_Tables")
    if report_tables_dst:
        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={report_tables_src}/"
        headers = get_supabase_headers()
        list_resp = requests.get(list_url, headers=headers)
        if list_resp.status_code == 200:
            for item in list_resp.json():
                filename = item["name"].split("/")[-1]
                src_path = item["name"]
                dst_path = f"{report_tables_dst}/{filename}"
                move_supabase_file(src_path, dst_path)

    # Question_Context — move all files
    question_src = "The_Big_Question/Predictive_Report/Question_Context"
    question_dst = target_map.get("Question_Context")
    if question_dst:
        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={question_src}/"
        list_resp = requests.get(list_url, headers=get_supabase_headers())
        if list_resp.status_code == 200:
            for item in list_resp.json():
                filename = item["name"].split("/")[-1]
                src_path = item["name"]
                dst_path = f"{question_dst}/{filename}"
                move_supabase_file(src_path, dst_path)

    # Logos — move all + copy logo
    logo_src = "The_Big_Question/Predictive_Report/Logos"
    logo_dst = target_map.get("Logos")
    if logo_dst:
        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={logo_src}/"
        list_resp = requests.get(list_url, headers=get_supabase_headers())
        if list_resp.status_code == 200:
            for item in list_resp.json():
                filename = item["name"].split("/")[-1]
                src_path = item["name"]
                dst_path = f"{logo_dst}/{filename}"
                move_supabase_file(src_path, dst_path)

        # COPY the Panelitix logo
        copy_supabase_file("The_Big_Question/General_Files/Panelitix_Logo.png", f"{logo_dst}/Panelitix_Logo.png")

    # Clean up .keep files
    delete_keep_files(folder_paths)

    return {"status": "complete", "message": "Files moved, renamed, and folders cleaned."}
