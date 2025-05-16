import re

def normalize_website(website: str) -> dict:
    # Remove URL scheme (http:// or https://) and 'www.' prefix if present
    domain = re.sub(r'^(?:https?://)?(?:www\.)?', '', website, flags=re.IGNORECASE)

    # Remove any trailing slash
    domain = domain.rstrip('/')

    # Add 'www.' prefix
    normalized_website = f"www.{domain}"

    return {"normalized_website": normalized_website}
