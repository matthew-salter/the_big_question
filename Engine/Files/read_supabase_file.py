import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def read_supabase_file(path: str, binary: bool = False):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()

    try:
        logger.info(f"📥 Reading Supabase file from: {url}")
        response = requests.get(url, headers=headers)

        logger.info(f"🛰️ Supabase response status: {response.status_code}")
        logger.debug(f"📄 Content-Type: {response.headers.get('Content-Type')}")
        response.raise_for_status()

        if binary:
            logger.debug(f"✅ Binary file read successful, content size: {len(response.content)} bytes")
            return response.content
        else:
            try:
                text = response.content.decode("utf-8", errors="strict")
                logger.debug(f"✅ Text file read successful (UTF-8), size: {len(text)} characters")
                return text
            except UnicodeDecodeError as e:
                logger.error(f"❌ UTF-8 decode failed: {e}")
                raise

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Supabase file read failed: {e}")
        raise
