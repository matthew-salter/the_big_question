import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

# Define expected keys
INTRO_KEYS = [
    "Client:", "Website:", "About Client:", "Main Question:", "Report:", "Year:",
    "Report Title:", "Report Sub-Title:", "Executive Summary:", "Key Findings:",
    "Call to Action:", "Report Change Title:", "Report Change:"
]
OUTRO_KEYS = ["Conclusion:", "Recommendations:"]
ALL_KEYS = INTRO_KEYS + OUTRO_KEYS

def strip_excluded_blocks(text):
    # Strip Report Table and Section Tables from parsing scope
    text = re.sub(r"(Report Table:\n)(.*?)(?=\nSection #:|\Z)", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(Section Tables:\n)(.*?)(?=\nSub-Section #:|\Z)", r"\1", text, flags=re.DOTALL)
    return text

def extract_intro_outro_assets(text: str) -> dict:
    asset_map = {}
    lines = text.splitlines()
    current_key = None
    buffer = []

    def commit_buffer(key, buf):
        cleaned = "\n".join(buf).strip().replace("\r\n", "\n").replace("\n", "\\n")
        csv_key = key.rstrip(":").lower().replace(" ", "_")
        asset_map[csv_key] = cleaned

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ALL_KEYS:
            if current_key and buffer:
                commit_buffer(current_key, buffer)
            current_key = stripped
            buffer = []
        elif current_key:
            if stripped == "" and i + 1 < len(lines) and lines[i + 1].strip().endswith(":"):
                # End of block, commit
                commit_buffer(current_key, buffer)
                current_key = None
                buffer = []
            else:
                buffer.append(line)

    # Final commit
    if current_key and buffer:
        commit_buffer(current_key, buffer)

    # Ensure all expected columns exist
    for key in ALL_KEYS:
        k = key.rstrip(":").lower().replace(" ", "_")
        asset_map.setdefault(k, "")

    return asset_map

# Leave this in but commented out until reintegration
# def parse_sections_and_subsections(text: str):
#     ...

def run_prompt(payload):
    logger.info("📦 Running csv_content.py (intro/outro mode)")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    raw_text = strip_excluded_blocks(payload.get("format_combine", ""))

    # Process only intro/outro for now
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
