import os
import requests
from datetime import datetime
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

SUPABASE_BUCKET = "panelitix"


def get_file_extension(url):
    return os.path.splitext(url.split("?")[0])[1].lstrip(".")


def fetch_file_contents(url):
    res = requests.get(url)
    res.raise_for_status()
    return res.content


def process_typeform_submission(data):
    try:
        logger.info("🚀 Processing Typeform submission")

        answers = data["form_response"]["answers"]
        client_name = None
        question_context_url = None
        logo_url = None

        for answer in answers:
            field_id = answer["field"]["id"]

            if field_id == "AHtYeYezxSPh":  # Client name
                client_name = answer["text"].replace(" ", "_").lower()

            elif field_id == "94zGg79WPuGQ":  # Question context file
                question_context_url = answer["file_url"]

            elif field_id == "EhqqF9jjQwTd":  # Logo file
                logo_url = answer["file_url"]

        if not client_name or not question_context_url or not logo_url:
            raise ValueError("Missing one or more required fields from Typeform")

        # Format date
        date_str = datetime.utcnow().strftime("%d-%m-%Y")

        # Write Question Context
        qc_content = fetch_file_contents(question_context_url).decode("utf-8")
        qc_path = f"public/The_Big_Question/Predicitive_Report/Question_Context/{client_name}_question_context_{date_str}.txt"
        write_supabase_file(qc_path, qc_content)
        logger.info(f"✅ Saved Question Context to: {qc_path}")

        # Write Logo
        logo_ext = get_file_extension(logo_url)
        logo_path = f"public/The_Big_Question/Predicitive_Report/Logo.{logo_ext}"
        logo_content = fetch_file_contents(logo_url)
        write_supabase_file(logo_path, logo_content)
        logger.info(f"✅ Saved Logo to: {logo_path}")

        return {
            "status": "success",
            "client": client_name,
            "question_context_path": qc_path,
            "logo_path": logo_path
        }

    except Exception as e:
        logger.exception("❌ Failed to process Typeform submission")
        return {"status": "error", "message": str(e)}
