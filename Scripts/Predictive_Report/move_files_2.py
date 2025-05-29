def move_file(source_path: str, target_path: str) -> bool:
    """Moves a file in Supabase from source_path to target_path."""
    headers = get_supabase_headers()
    headers["Content-Type"] = "application/json"
    url = f"{SUPABASE_URL}/storage/v1/object/move"
    data = {
        "bucketId": SUPABASE_BUCKET,
        "sourceKey": source_path,
        "destinationKey": target_path
    }

    try:
        logger.info(f"🔀 Moving {source_path} → {target_path}")
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        logger.info("✅ Move successful")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Move failed: {e}")
        return False

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

    # --- Stage 1 Output (unchanged)
    source_folder_files = {}
    for folder, files in stage_1_results.items():
        readable_label = f"Source Folder {folder.replace('/', ' ')}"
        source_folder_files[readable_label] = [file for file in files]

    output = {
        "source_folder_files": source_folder_files
    }

    for folder, status in stage_2_results.items():
        flat_key = f"target_folder__{folder.replace('/', '_')}"
        output[flat_key] = status

    # --- Stage 3: Move files from source to matched target folder
    logger.info("🚀 Starting Stage 3: Moving files to target folders")
    for src_folder, file_list in stage_1_results.items():
        suffix = None
        if "Report_and_Section_Tables" in src_folder:
            suffix = "/Report_and_Section_Tables/"
        elif "Logos" in src_folder:
            suffix = "/Logos/"
        elif "Question_Context" in src_folder:
            suffix = "/Question_Context/"
        else:
            continue

        # Find corresponding target folder from stage 2
        matching_target = None
        for target in stage_2_results.keys():
            if target.endswith(suffix):
                matching_target = target
                break

        if not matching_target or stage_2_results[matching_target] != "found":
            logger.warning(f"⚠️ No valid target folder found for {src_folder}")
            continue

        for fname in file_list:
            if fname == ".emptyFolderPlaceholder":
                continue
            source_path = f"{src_folder}/{fname}"
            dest_path = f"{matching_target}/{fname}"
            move_file(source_path, dest_path)

    logger.info("📦 Completed Stage 3")

    return output

