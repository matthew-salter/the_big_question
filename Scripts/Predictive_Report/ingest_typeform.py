import os
import requests
from datetime import datetime
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file


def download_file(url: str) -> bytes:
    """Downloads a file from a given URL and returns its binary content."""
    res = requests.get(url)
    res.raise_for_status()
    return res.content


def run_prompt(data):
    try:
        answers = data.get("form_response", {}).get("answers", [])
        client = None
        question_context_url = None
        logo_url = None
        logo_ext = None

        for answer in answers:
            field_id = answer["field"]["id"]

            if field_id == "AHtYeYezxSPh":  # Client name
                client = answer["text"].strip().replace(" ", "_")

            elif field_id == "94zGg79WPuGQ":  # Question context file
                question_context_url = answer["file_url"]

            elif field_id == "EhqqF9jjQwTd":  # Logo file
                logo_url = answer["file_url"]
                logo_ext = os.path.splitext(logo_url.split("/")[-1])[-1]  # .jpg or .png

        if not client or not question_context_url or not logo_url:
            raise ValueError("Missing required fields: client, question context file, or logo")

        # Format filenames and paths
        date_str = datetime.utcnow().strftime("%d-%m-%Y")
        question_context_path = f"public/The_Big_Question/Predictive_Report/Question_Context/{client}_question_context_{date_str}.txt"
        logo_path = f"public/The_Big_Question/Predictive_Report/Logo.{logo_ext.lstrip('.')}"

        # Download and write the question context
        logger.info(f"📥 Downloading question context from: {question_context_url}")
        question_context_data = download_file(question_context_url)
        write_supabase_file(question_context_path, question_context_data.decode("utf-8"))

        # Download and write the logo file
        logger.info(f"📥 Downloading logo from: {logo_url}")
        logo_data = download_file(logo_url)
        write_supabase_file(logo_path, logo_data)

        logger.info("✅ Files written to Supabase successfully.")

    except Exception:
        logger.exception("❌ Failed to process Typeform submission and save files to Supabase.")
