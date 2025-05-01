import requests
from Engine.Supabase.auth import supabase_headers

def write_supabase_file(path, content):
    url = f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/{path}"
    headers = supabase_headers()
    response = requests.put(url, headers=headers, data=content)
    if not response.ok:
        raise Exception(f"Failed to write to Supabase: {response.status_code}, {response.text}")

