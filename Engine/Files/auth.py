import os

def supabase_headers():
    token = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "apikey": token,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }
