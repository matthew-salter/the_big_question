import requests
from auth import get_supabase_headers
from logger import logger

SUPABASE_URL = "https://<your-project-id>.supabase.co"
SUPABASE_BUCKET = "panelitix"

def write_supabase_file(path, content: str):
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()
    data = content.encode("utf-8")

    res = requests.put(url, headers=headers, data=data)
    res.raise_for_status()
