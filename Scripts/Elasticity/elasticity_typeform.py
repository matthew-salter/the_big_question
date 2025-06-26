import os
import requests
import time
from datetime import datetime
from pathlib import Path
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- ENV VARS ---
supply_field_id = os.getenv("SUPPLY_FIELD_ID")
demand_field_id = os.getenv("DEMAND_FIELD_ID")
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER")
SUPABASE_URL = os.getenv("SUPABASE_URL")

logger.info("🌍 ENV VARS (elasticity_typeform.py):")
logger.info(f"   SUPPLY_FIELD_ID = {supply_field_id}")
logger.info(f"   DEMAND_FIELD_ID = {demand_field_id}")
logger.info(f"   SUPABASE_ROOT_FOLDER = {SUPABASE_ROOT_FOLDER}")
logger.info(f"   SUPABASE_URL = {SUPABASE_URL}")

# --- HELPERS ---
def download_file(url: str, retries: int = 3, delay: int = 2) -> bytes:
    """Download with optional Typeform token."""
    headers = {}
    if "api.typeform.com/responses/files" in url:
        typeform_token = os.getenv("TYPEFORM_TOKEN")
        if not typeform_token:
            raise EnvironmentError("TYPEFORM_TOKEN not set")
        headers["Authorization"] = f"Bearer {typeform_token}"

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🌐 Attempt {attempt} download: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            logger.info(f"📥 Downloaded {len(res.content)} bytes")
            return res.content
        except requests.RequestException as e:
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(delay)

# --- MAIN ---
def process_typeform_submission(data):
    try:
        answers = data.get("form_response", {}).get("answers", [])
        submitted_at = data.get("form_response", {}).get("submitted_at")
        if submitted_at:
            logger.info(f"🕒 Typeform submitted_at: {submitted_at}")
        logger.info(f"🕒 Script start: {datetime.utcnow().isoformat()}")

        supply_url = None
        demand_url = None

        logger.info("📦 Scanning answers for file uploads...")
        for answer in answers:
            field_id = answer["field"]["id"]
            if field_id == supply_field_id:
                supply_url = answer["file_url"]
                logger.info(f"📄 Supply file URL: {supply_url}")
            elif field_id == demand_field_id:
                demand_url = answer["file_url"]
                logger.info(f"📄 Demand file URL: {demand_url}")

        if not supply_url or not demand_url:
            raise ValueError("Missing supply or demand file URLs.")

        # Build destination paths
        date_str = datetime.utcnow().strftime("%d-%m-%Y")
        supply_filename = supply_url.split("/")[-1]
        demand_filename = demand_url.split("/")[-1]

        supply_path = f"{SUPABASE_ROOT_FOLDER}/Elasticity/Supply_Report/{supply_filename}"
        demand_path = f"{SUPABASE_ROOT_FOLDER}/Elasticity/Demand_Report/{demand_filename}"

        logger.info("🧾 Supabase paths:")
        logger.info(f"   Supply: {supply_path}")
        logger.info(f"   Demand: {demand_path}")

        # Download & write files
        logger.info(f"⬇️ Downloading supply file")
        supply_data = download_file(supply_url)
        write_supabase_file(supply_path, supply_data)

        logger.info(f"⬇️ Downloading demand file")
        demand_data = download_file(demand_url)
        write_supabase_file(demand_path, demand_data)

        logger.info("✅ Files uploaded successfully to Supabase.")

    except Exception:
        logger.exception("❌ Error processing Typeform elasticity upload.")
import os
import requests
import time
from datetime import datetime
from pathlib import Path
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- ENV VARS ---
supply_field_id = os.getenv("SUPPLY_FIELD_ID")
demand_field_id = os.getenv("DEMAND_FIELD_ID")
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER")
SUPABASE_URL = os.getenv("SUPABASE_URL")

logger.info("🌍 ENV VARS (elasticity_typeform.py):")
logger.info(f"   SUPPLY_FIELD_ID = {supply_field_id}")
logger.info(f"   DEMAND_FIELD_ID = {demand_field_id}")
logger.info(f"   SUPABASE_ROOT_FOLDER = {SUPABASE_ROOT_FOLDER}")
logger.info(f"   SUPABASE_URL = {SUPABASE_URL}")

# --- HELPERS ---
def download_file(url: str, retries: int = 3, delay: int = 2) -> bytes:
    """Download with optional Typeform token."""
    headers = {}
    if "api.typeform.com/responses/files" in url:
        typeform_token = os.getenv("TYPEFORM_TOKEN")
        if not typeform_token:
            raise EnvironmentError("TYPEFORM_TOKEN not set")
        headers["Authorization"] = f"Bearer {typeform_token}"

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🌐 Attempt {attempt} download: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            logger.info(f"📥 Downloaded {len(res.content)} bytes")
            return res.content
        except requests.RequestException as e:
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(delay)

# --- MAIN ---
def process_typeform_submission(data):
    try:
        answers = data.get("form_response", {}).get("answers", [])
        submitted_at = data.get("form_response", {}).get("submitted_at")
        if submitted_at:
            logger.info(f"🕒 Typeform submitted_at: {submitted_at}")
        logger.info(f"🕒 Script start: {datetime.utcnow().isoformat()}")

        supply_url = None
        demand_url = None

        logger.info("📦 Scanning answers for file uploads...")
        for answer in answers:
            field_id = answer["field"]["id"]
            if field_id == supply_field_id:
                supply_url = answer["file_url"]
                logger.info(f"📄 Supply file URL: {supply_url}")
            elif field_id == demand_field_id:
                demand_url = answer["file_url"]
                logger.info(f"📄 Demand file URL: {demand_url}")

        if not supply_url or not demand_url:
            raise ValueError("Missing supply or demand file URLs.")

        # Build destination paths
        date_str = datetime.utcnow().strftime("%d-%m-%Y")
        supply_filename = supply_url.split("/")[-1]
        demand_filename = demand_url.split("/")[-1]

        supply_path = f"{SUPABASE_ROOT_FOLDER}/Elasticity/Supply_Report/{supply_filename}"
        demand_path = f"{SUPABASE_ROOT_FOLDER}/Elasticity/Demand_Report/{demand_filename}"

        logger.info("🧾 Supabase paths:")
        logger.info(f"   Supply: {supply_path}")
        logger.info(f"   Demand: {demand_path}")

        # Download & write files
        logger.info(f"⬇️ Downloading supply file")
        supply_data = download_file(supply_url)
        write_supabase_file(supply_path, supply_data)

        logger.info(f"⬇️ Downloading demand file")
        demand_data = download_file(demand_url)
        write_supabase_file(demand_path, demand_data)

        logger.info("✅ Files uploaded successfully to Supabase.")

    except Exception:
        logger.exception("❌ Error processing Typeform elasticity upload.")
