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
        res = requests.get(url, headers=headers)

        logger.info(f"Supabase response status: {res.status_code}")
        res.raise_for_status()

        if binary:
            logger.debug(f"✅ Binary file read successful, content size: {len(res.content)} bytes")
            return res.content
        else:
            logger.debug(f"✅ Text file read successful, content size: {len(res.text)} bytes")
            return res.text

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Supabase file read failed: {e}")
        raise
