from logger import logger
from datetime import datetime

def run_prompt(_: dict) -> dict:
    # Get current year and month
    now = datetime.now()
    current_year = now.year
    month = now.month

    # Determine year output based on quarter
    if month in [1, 2, 3]:  # Q1
        year_range = f"{current_year}"
    elif month in [4, 5, 6, 7, 8, 9]:  # Q2 or Q3
        next_year_suffix = f"'{str(current_year + 1)[-2:]}"
        year_range = f"{current_year} - {next_year_suffix}"
    else:  # Q4 (Oct–Dec)
        year_range = f"{current_year + 1}"

    return {"year": year_range}
