import requests
import json
import logging
from datetime import datetime
from Engine.Files.write_supabase_file import write_supabase_file

logger = logging.getLogger(__name__)

def process_typeform_submission(data):
    logger.info("📩 Typeform webhook triggered")
    logger.debug("Full Typeform payload:\n%s", json.dumps(data, indent=2))

    form_fields = {
        answer['field']['ref']: answer.get('text') or answer.get('email') or answer.get('choice', {}).get('label')
        for answer in data['form_response']['answers']
    }

    logger.info("🧩 Extracted Form Fields:")
    logger.debug("%s", json.dumps(form_fields, indent=2))

    file_field = next((a for a in data['form_response']['answers'] if a['type'] == 'file_url'), None)
    if not file_field:
        logger.error("❌ Missing file upload in Typeform.")
        raise Exception("Missing file upload in Typeform.")

    file_url = file_field['file_url']
    logger.info("⬇️ Downloading file from: %s", file_url)

    try:
        file_response = requests.get(file_url)
        file_response.raise_for_status()
        file_content = file_response.text
    except Exception as e:
        logger.exception("❌ Failed to download uploaded file.")
        raise

    client_name = form_fields.get('26f95c88-43d4-4540-83b7-0d78e1c9535e', 'unknown').replace(" ", "_")
    timestamp = datetime.utcnow().strftime('%d%m%Y_%H%M')
    filename = f"{client_name}_Question_Context{timestamp}.txt"
    supabase_path = f"panelitix/The Big Question/Predictive Report/Question Context/{filename}"

    logger.info("📤 Writing file to Supabase: %s", supabase_path)

    try:
        write_supabase_file(supabase_path, file_content)
    except Exception as e:
        logger.exception("❌ Supabase write failed.")
        raise

    logger.info("✅ File successfully uploaded to Supabase.")

    return {
        "prompt": "client_context",
        "client": form_fields.get("26f95c88-43d4-4540-83b7-0d78e1c9535e", ""),
        "client_context_url": f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{supabase_path}"
    }

