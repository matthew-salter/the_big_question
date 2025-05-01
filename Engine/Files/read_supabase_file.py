import requests
import time

def read_supabase_file(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            print(f"🔄 Attempt {attempt}: Fetching {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            print("✅ File fetched successfully.")
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise Exception(f"❌ All attempts to fetch the file failed: {e}")
