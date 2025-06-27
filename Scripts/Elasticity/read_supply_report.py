import time
from datetime import datetime
from logger import logger
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "panelitix")
ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER", "The_Big_Question")

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def run_prompt(data):
    try:
        target_folder = f"{ROOT_FOLDER}/Elasticity/Supply_Report"

        logger.info(f"📁 Listing files in: {target_folder}")
        file_list = supabase.storage.from_(SUPABASE_BUCKET).list(target_folder)

        if not file_list:
            return "No supply report files found in Supabase."

        # Sort by timestamp (descending), use `updated_at` or `created_at` if available
        file_list.sort(key=lambda x: x.get("last_modified") or x.get("updated_at") or x.get("created_at"), reverse=True)

        most_recent_file = file_list[0]["name"]
        supabase_path = f"{target_folder}/{most_recent_file}"

        logger.info(f"📄 Most recent supply report: {most_recent_file}")

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.info(f"📥 Attempting to read: {supabase_path} (try {retries + 1})")
                response = supabase.storage.from_(SUPABASE_BUCKET).download(supabase_path)
                content = response.decode("utf-8")
                logger.info("✅ File read successfully")
                return content.strip()
            except Exception as e:
                logger.warning(f"Retry {retries + 1}: {e}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        return f"❌ Max retries exceeded. Could not read file: {most_recent_file}"

    except Exception as e:
        logger.exception("❌ Error in read_supply_report")
        return f"Server error while reading supply report: {str(e)}"
