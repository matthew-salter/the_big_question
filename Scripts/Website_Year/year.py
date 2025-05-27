from logger import logger
from datetime import datetime

def run_prompt(_: dict) -> dict:
    # Get current date
    now = datetime.now()

    # Format month as 3-letter abbreviation and year as 4-digit number
    formatted_date = now.strftime("%b %Y")  # e.g. "May 2025"

    return {"year": formatted_date}
