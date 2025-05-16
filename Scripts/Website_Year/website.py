import re
from logger import logger

def normalize_website(website: str) -> str:
    domain = re.sub(r'^(?:https?://)?(?:www\.)?', '', website, flags=re.IGNORECASE)
    domain = domain.rstrip('/')
    return f"www.{domain}"

def run_prompt(data: dict) -> dict:
    website = data.get("client_website_url")
    if not website:
        return {"error": "Missing client_website_url"}
    return {"normalized_website": normalize_website(website)}
