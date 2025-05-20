import csv
import io
import uuid
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

def run_prompt(payload):
    logger.info("📦 Running csv_content.py")

    # Get or create run_id
    run_id = payload.get("run_id") or str(uuid.uuid4())
    logger.debug(f"🆔 Using run_id: {run_id}")

    # Define the Supabase file path
    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    logger.debug(f"🗂️ Target Supabase path: {file_path}")

    # --- Write CSV to memory ---
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["TEST"])
    csv_bytes = output.getvalue().encode("utf-8")

    # --- Upload to Supabase ---
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")

    # --- Read the uploaded CSV back as text ---
    csv_text = read_supabase_file(path=file_path, binary=False)

    # --- Return to Zapier ---
    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
