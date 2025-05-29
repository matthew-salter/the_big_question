import os
import logging
from Engine.Files.read_copy_supabase_file import read_copy_supabase_file
from Engine.Files.write_copy_supabase_file import write_copy_supabase_file

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def run_prompt(payload: dict) -> dict:
    run_id = payload.get("run_id")
    client_name = payload.get("client_name")
    report_title = payload.get("report_title")
    timestamp_folder = payload.get("timestamp_folder")
    expected_folders = payload.get("expected_folders", "")

    folder_keys = ["Logos", "Question_Context", "Report_and_Section_Tables"]
    source_base_paths = {
        "Logos": "The_Big_Question/Predictive_Report/Logos",
        "Question_Context": "The_Big_Question/Predictive_Report/Question_Context",
        "Report_and_Section_Tables": "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
    }

    # Find target paths from expected_folders based on suffix
    target_paths = {
        key: path for key in folder_keys
        for path in expected_folders.split(",")
        if path.endswith(f"/{key}")
    }

    output = {
        "source_folders": [],
        "target_folders": [],
        "moved_files": [],
        "errors": [],
    }

    logger.info("🚀 Stage 1: Reading source folders")
    source_folder_files = {}
    for key, source_path in source_base_paths.items():
        try:
            files = read_copy_supabase_file(source_path)
            files = [f for f in files if f != ".emptyFolderPlaceholder"]
            source_folder_files[key] = files
            output["source_folders"].append({"folder": source_path, "files": files})
            logger.info(f"✅ Found files in source folder: {source_path}")
        except Exception as e:
            logger.error(f"❌ Error reading folder {source_path}: {str(e)}")
            output["errors"].append({"folder": source_path, "error": str(e)})

    logger.info("🚀 Stage 2: Validating target folders")
    for key, target_path in target_paths.items():
        try:
            _ = read_copy_supabase_file(target_path)
            output["target_folders"].append({"folder": target_path, "found": True})
            logger.info(f"✅ Target folder confirmed: {target_path}")
        except Exception as e:
            logger.warning(f"⚠️ No valid target folder for: {target_path}")
            output["target_folders"].append({"folder": target_path, "found": False})
            output["errors"].append({"folder": target_path, "error": str(e)})

    logger.info("🚀 Stage 3: Moving files from source to target")
    for key, files in source_folder_files.items():
        source_path = source_base_paths[key]
        target_path = target_paths.get(key)

        if not target_path:
            logger.warning(f"⚠️ Skipping {key} - no target folder found")
            continue

        for file in files:
            try:
                full_source = f"{source_path}/{file}"
                full_target = f"{target_path}/{file}"
                data = read_copy_supabase_file(full_source, return_bytes=True)
                write_copy_supabase_file(full_target, data)
                write_copy_supabase_file(full_source, None, delete=True)

                logger.info(f"📥 Moved {file} to {full_target}")
                output["moved_files"].append({
                    "file": file,
                    "from": full_source,
                    "to": full_target
                })
            except Exception as e:
                logger.error(f"❌ Error moving file {file}: {str(e)}")
                output["errors"].append({"file": file, "error": str(e)})

    return output
