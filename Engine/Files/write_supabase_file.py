import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def write_supabase_file(path, content):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()

    if isinstance(content, str):
        try:
            # Validate UTF-8 encoding explicitly
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

    # Ensure correct content-type with charset
    headers["Content-Type"] = "text/plain; charset=utf-8"

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
