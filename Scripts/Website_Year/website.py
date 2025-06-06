import re
from logger import logger

def normalize_website(website: str) -> str:
    # Remove protocol and 'www.'
    domain = re.sub(r'^(?:https?:\/\/)?(?:www\.)?', '', website, flags=re.IGNORECASE)
    
    # Remove trailing slash or path
    domain = domain.split('/')[0].strip()

    # Defensive fallback: if domain is empty, raise an error
    if not domain or '.' not in domain:
        raise ValueError(f"Invalid domain after processing: '{website}' → '{domain}'")

    return f"www.{domain}"

def run_prompt(data: dict) -> dict:
    try:
        website = data.get("client_website_url", "").strip()
        if not website:
            return {"error": "Missing client_website_url"}
        
        normalized = normalize_website(website)
        return {"normalized_website": normalized}
    
    except Exception as e:
        logger.exception("❌ Failed to normalize website")
        return {"error": f"Website normalisation failed: {str(e)}"}
