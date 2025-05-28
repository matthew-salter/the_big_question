# move_files_2.py — Stage 1: List files in static source folders

import os
import requests
from logger import logger
from Engine.Files.auth import get_supabase_headers

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

SOURCE_FOLDERS = [
    "The_Big_Question/Predictive_Report/Logos",
    "The_Big_Question/Predictive_Report/Question_Context",
    "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
]

def list_files_in_folder(folder_path: str):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    headers = get_supabase_headers()
    params = {"prefix": folder_path, "limit": 1000}

    try:
        logger.info(f"📂 Listing files in folder: {folder_path}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        files = response.json()

        file_names = [file['name'].split('/')[-1] for file in files if not file['name'].endswith('/')]
        logger.info(f"🧾 Files found: {file_names}")
        return file_names

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to list files in {folder_path}: {e}")
        return []

def main():
    results = {}
    for folder in SOURCE_FOLDERS:
        file_names = list_files_in_folder(folder)
        results[folder] = file_names

    for folder, files in results.items():
        logger.info(f"📁 {folder} contains: {files}")

if __name__ == "__main__":
    main()



if __name__ == "__main__":
    app.run(debug=True)
