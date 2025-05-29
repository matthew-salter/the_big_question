import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def write_supabase_file(path, content, content_type=None):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()

    # --- Encode content ---
    if isinstance(content, str):
        try:
            data = content.encode("utf-8", errors="strict")
            logger.debug("📄 Content is valid UTF-8 string. Encoding before upload.")
        except UnicodeEncodeError as e:
            logger.error(f"❌ UTF-8 encoding failed: {e}")
            raise
    elif isinstance(content, bytes):
        data = content
        logger.debug("🖼️ Content is raw bytes. Uploading directly.")
    else:
        raise TypeError("❌ Content must be either str or bytes.")

    # --- Determine Content-Type ---
    if content_type:
        headers["Content-Type"] = content_type
        logger.debug(f"🧾 Custom Content-Type provided: {content_type}")
    elif path.endswith(".csv"):
        headers["Content-Type"] = "text/csv; charset=utf-8"
        logger.debug("🧾 CSV file detected. Using Content-Type: text/csv")
    else:
        headers["Content-Type"] = "text/plain; charset=utf-8"
        logger.debug("📑 Defaulting to Content-Type: text/plain")

    # --- Upload to Supabase ---
    try:
        logger.info(f"🚀 Attempting Supabase file write to: {url}")
        logger.debug(f"📦 Upload headers: {headers}")
        logger.debug(f"📏 Upload size: {len(data)} bytes")

        response = requests.put(url, headers=headers, data=data)

        logger.info(f"📡 Supabase status: {response.status_code}")
        logger.debug(f"📨 Supabase response: {response.text}")

        response.raise_for_status()
        logger.info("✅ File write to Supabase successful.")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Supabase file write failed: {e}")
        raise
