import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

# Define the intro and outro keys in order
INTRO_KEYS = [
    "Client:", "Website:", "About Client:", "Main Question:", "Report:", "Year:",
    "Report Title:", "Report Sub-Title:", "Executive Summary:", "Key Findings:",
    "Call to Action:", "Report Change Title:", "Report Change:"
]
OUTRO_KEYS = ["Conclusion:", "Recommendations:"]
ALL_KEYS = INTRO_KEYS + OUTRO_KEYS

def extract_intro_outro_assets(text: str) -> dict:
    asset_map = {}
    pattern = re.compile(rf"({'|'.join([re.escape(k) for k in ALL_KEYS])})\n(.*?)(?=\n(?:{'|'.join([re.escape(k) for k in ALL_KEYS])})\n|\Z)", re.DOTALL)

    for match in pattern.finditer(text):
        key_raw, block = match.groups()
        key = key_raw.rstrip(":").lower().replace(" ", "_")
        clean_value = block.strip().replace("\r\n", "\n").replace("\n", "\\n")
        asset_map[key] = clean_value

    # Ensure all fields are present
    for key in ALL_KEYS:
        k = key.rstrip(":").lower().replace(" ", "_")
        asset_map.setdefault(k, "")

    return asset_map

    # Ensure all fields are present
    for key in ALL_KEYS:
        k = key.rstrip(":").lower().replace(" ", "_")
        asset_map.setdefault(k, "")

    return asset_map

# Preserve full parse_sections_and_subsections for later, but comment out use
# def parse_sections_and_subsections(text: str):
#     ...

def run_prompt(payload):
    logger.info("📦 Running csv_content.py (intro/outro only)")
    run_id = payload.get("run_id") or str(uuid.uuid4())
    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    raw_text = payload.get("format_combine", "")

    # Only extract intro/outro for now
    intro_outro_row = extract_intro_outro_assets(raw_text)
    rows = [intro_outro_row]

    header_order = list(intro_outro_row.keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header_order)
    writer.writeheader()
    writer.writerows(rows)

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
