import requests
from Engine.Files.auth import get_supabase_headers
from logger import logger

SUPABASE_URL = "https://<your-project-id>.supabase.co"
SUPABASE_BUCKET = "panelitix"

def read_supabase_file(path: str) -> str:
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    headers = get_supabase_headers()
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.text
