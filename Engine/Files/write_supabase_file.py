import requests
import logging
from Engine.Files.auth import supabase_headers

logger = logging.getLogger(__name__)

def write_supabase_file(path, content):
    url = f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/{path}"
    headers = supabase_headers()
    logger.info(f"📤 Writing file to Supabase: {url}")
    response = requests.put(url, headers=headers, data=content)
    if not response.ok:
        logger.error(f"❌ Failed to write to Supabase: {response.status_code}, {response.text}")
        raise Exception(f"Failed to write to Supabase: {response.status_code}, {response.text}")
    logger.info(f"✅ Successfully wrote file to Supabase at: {url}")
