import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

# Fixed asset title → CSV fieldname mapping
ASSET_MAPPING = {
    "Report Title:": "report_title",
    "Client:": "client",
    "Commodity:": "commodity",
    "Report Date:": "report_date",
    "Region:": "region",
    "Time Range:": "time_period",
    "Report Executive Summary:": "report_executive_summary",
    "Supply Change:": "supply_change",
    "Supply Elasticity:": "supply_elasticity",
    "Supply Summary:": "supply_summary",
    "Demand Change:": "report_change",  # ← special mapping
    "Demand Elasticity:": "demand_elasticity",
    "Demand Summary:": "demand_summary",
    "Elasticity Change:": "elasticity_change",
    "Elasticity Summary:": "elasticity_summary",
    "Elasticity Calculation:": "elasticity_calculation"
}

def extract_asset_fields(text):
    result = {}
    current_key = None
    buffer = []

    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ASSET_MAPPING:
            if current_key and buffer:
                field = ASSET_MAPPING[current_key]
                content = "\n".join(buffer).strip().replace("\n", "\\n")
                result[field] = content
            current_key = stripped
            buffer = []
        elif current_key:
            buffer.append(line)

    # Final asset
    if current_key and buffer:
        field = ASSET_MAPPING[current_key]
        content = "\n".join(buffer).strip().replace("\n", "\\n")
        result[field] = content

    # Ensure all fields exist
    for field in ASSET_MAPPING.values():
        result.setdefault(field, "")

    return result

def run_prompt(payload):
    logger.info("📦 Running elasticity_csv.py")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    file_path = f"Elasticity/Ai_Responses/Elasticity_csv/{run_id}.csv"
    raw_text = payload.get("elasticity_combine", "")

    row_data = extract_asset_fields(raw_text)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ASSET_MAPPING.values())
    writer.writeheader()
    writer.writerow(row_data)

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
