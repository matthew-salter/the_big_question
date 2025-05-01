import requests
import os

def write_supabase_file(path, content):
    url = f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/{path}"
    headers = {
        "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY')}",
        "Content-Type": "text/plain",
    }
    response = requests.put(url, headers=headers, data=content)
    if not response.ok:
        raise Exception(f"Failed to write to Supabase: {response.status_code}, {response.text}")
