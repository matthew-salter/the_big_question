import os
import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_BUCKET = "panelitix"

def write_supabase_file(path, content: str):
    if not SUPABASE_URL:
        logger.error("❌ SUPABASE_URL is not set in environment variables.")
        raise ValueError("SUPABASE_URL not configured")

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()
    data = content.encode("utf-8")

    try:
        logger.info(f"Attempting Supabase file write to: {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data size: {len(data)} bytes")

        res = requests.put(url, headers=headers, data=data)

        logger.info(f"Supabase response status: {res.status_code}")
        logger.debug(f"Supabase response body: {res.text}")

        res.raise_for_status()
        logger.info("✅ File write to Supabase successful.")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Supabase file write failed: {e}")
        raise
