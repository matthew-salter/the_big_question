import os
import requests
import time
from datetime import datetime
from pathlib import Path
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- ENV VARS ---
client_field_id = os.getenv("CLIENT_FIELD_ID")
question_context_field_id = os.getenv("QUESTION_CONTEXT_FIELD_ID")
logo_field_id = os.getenv("LOGO_FIELD_ID")
SUPABASE_ROOT_FOLDER = os.getenv("SUPABASE_ROOT_FOLDER")
SUPABASE_URL = os.getenv("SUPABASE_URL")

logger.info("🌍 ENV VARS (ingest_typeform.py):")
logger.info(f"   CLIENT_FIELD_ID = {client_field_id}")
logger.info(f"   QUESTION_CONTEXT_FIELD_ID = {question_context_field_id}")
logger.info(f"   LOGO_FIELD_ID = {logo_field_id}")
logger.info(f"   SUPABASE_ROOT_FOLDER = {SUPABASE_ROOT_FOLDER}")
logger.info(f"   SUPABASE_URL = {SUPABASE_URL}")

# --- HELPERS ---
def download_file(url: str, retries: int = 3, delay: int = 2) -> bytes:
    """Downloads a file from a given URL and returns its binary content, with Typeform auth if needed."""
    headers = {}

    if "api.typeform.com/responses/files" in url:
        typeform_token = os.getenv("TYPEFORM_TOKEN")
        if not typeform_token:
            raise EnvironmentError("TYPEFORM_TOKEN not set in environment variables")
        headers["Authorization"] = f"Bearer {typeform_token}"

    for attempt in range(1, retries + 1):
        logger.info(f"🌐 Attempting download (try {attempt}) from URL: {url}")
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                logger.warning(f"📡 HTTP {res.status_code} - Response headers: {res.headers}")
                logger.warning(f"📡 Response content preview: {res.content[:200]}")
            res.raise_for_status()
            logger.info(f"📥 Download successful (size = {len(res.content)} bytes)")
            return res.content
        except requests.RequestException as e:
            logger.warning(f"⚠️ Download failed (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                logger.error(f"❌ Failed to download file after {retries} attempts: {url}")
                raise

# --- MAIN FUNCTION ---
def process_typeform_submission(data):
    """Extracts client, context, and logo file from Typeform and writes to Supabase."""
    try:
        answers = data.get("form_response", {}).get("answers", [])
        submitted_at = data.get("form_response", {}).get("submitted_at")
        if submitted_at:
            logger.info(f"🕒 Typeform submitted_at: {submitted_at}")
        logger.info(f"🕒 Script start time: {datetime.utcnow().isoformat()}")

        client = None
        question_context_url = None
        logo_url = None
        logo_ext = None

        logger.info("📦 Parsing Typeform answers...")
        for answer in answers:
            field_id = answer["field"]["id"]
            logger.debug(f"🧩 Field ID: {field_id}, Type: {answer['type']}")

            if field_id == client_field_id:
                client = answer["text"].strip().replace(" ", "_")
                logger.info(f"👤 Client parsed: {client}")

            elif field_id == question_context_field_id:
                question_context_url = answer["file_url"]
                logger.info(f"📄 Question context file URL: {question_context_url}")

            elif field_id == logo_field_id:
                logo_url = answer["file_url"]
                logo_filename = logo_url.split("/")[-1]
                logo_ext = Path(logo_filename).suffix.lstrip(".")
                logger.info(f"🖼️ Logo file URL: {logo_url}")
                logger.info(f"🖼️ Detected logo extension: {logo_ext}")
                if not logo_ext:
                    raise ValueError(f"Could not determine file extension from logo_url: {logo_url}")

        if not client or not question_context_url or not logo_url:
            raise ValueError("❌ Missing required fields: client, question context file, or logo")

        date_str = datetime.utcnow().strftime("%d-%m-%Y")
        question_context_path = f"Predictive_Report/Question_Context/{client}_question_context_{date_str}.txt"
        logo_path = f"Predictive_Report/Logos/{client}_Logo_{date_str}.{logo_ext}"

        logger.info("🧾 Final Supabase paths:")
        logger.info(f"   Question Context: {question_context_path}")
        logger.info(f"   Logo: {logo_path}")

        # --- Question Context ---
        logger.info(f"⬇️ Downloading question context from: {question_context_url}")
        question_context_data = download_file(question_context_url)

        try:
            decoded_context = question_context_data.decode("utf-8")
            logger.info("✅ Decoded question context as UTF-8 successfully")
        except UnicodeDecodeError as e:
            logger.error(f"❌ Failed to decode question context file as UTF-8: {e}")
            raise

        logger.info(f"🔎 Context content preview (first 100 chars): {repr(decoded_context[:100])}")
        logger.info(f"📏 Context length (chars): {len(decoded_context)}")
        write_supabase_file(question_context_path, decoded_context)

        # --- Logo ---
        logger.info(f"⬇️ Downloading logo from: {logo_url}")
        logo_data = download_file(logo_url)
        logger.info(f"📏 Logo file size: {len(logo_data)} bytes")
        logger.info(f"🔎 Logo content preview (first 20 bytes): {logo_data[:20]}")
        write_supabase_file(logo_path, logo_data)

        logger.info("✅ Files written to Supabase successfully.")

    except Exception:
        logger.exception("❌ Failed to process Typeform submission and save files to Supabase.")
