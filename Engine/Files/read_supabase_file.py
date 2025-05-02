import requests
import time
import logging

logger = logging.getLogger(__name__)

def read_supabase_file(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🔄 Attempt {attempt}: Fetching {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            logger.info("✅ File fetched successfully.")
            return response.text
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                logger.error(f"❌ All attempts to fetch the file failed: {e}")
                raise Exception(f"All attempts to fetch the file failed: {e}")
