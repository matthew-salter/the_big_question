from logger import logger
from datetime import datetime

def run_prompt(_: dict) -> dict:
    # Get the current year
    current_year = datetime.now().year

    # Calculate the next year
    next_year = current_year + 1

    # Format next year as "'YY" (e.g., '26 for 2026)
    formatted_next_year = f"'{str(next_year)[-2:]}"

    # Combine into the desired output format
    year_range = f"{current_year} - {formatted_next_year}"

    return {"year": year_range}
