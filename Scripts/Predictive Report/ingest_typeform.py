import requests
import json
from datetime import datetime
from Engine.Files.write_supabase_file import write_supabase_file
from logger import logger

def process_typeform_submission(data):
    logger.info("📩 Typeform webhook triggered")
    logger.debug("Full Typeform payload:\n%s", json.dumps(data, indent=2))

    form_fields = {
        answer['field']['ref']: answer.get('text') or answer.get('email') or answer.get('choice', {}).get('label')
        for answer in data['form_response']['answers']
    }

    logger.info("🧩 Extracted Form Fields:")
    logger.debug("%s", json.dumps(form_fields, indent=2))

    answers = data['form_response']['answers']

    # === Step 1: Process Question Context ===
    context_field = next((a for a in answers if a['field']['ref'] == 'df96b970-1262-4202-9b7d-96cf6b7b4e76'), None)
    if not context_field:
        logger.error("❌ Missing question context file in Typeform.")
        raise Exception("Missing question context file in Typeform.")

    context_url = context_field['file_url']
    logger.info("⬇️ Downloading question context file from: %s", context_url)

    try:
        context_response = requests.get(context_url)
        context_response.raise_for_status()
        context_content = context_response.text
    except Exception as e:
        logger.exception("❌ Failed to download question context file.")
        raise

    client_name = form_fields.get('26f95c88-43d4-4540-83b7-0d78e1c9535e', 'unknown').replace(" ", "_")
    timestamp = datetime.utcnow().strftime('%d%m%Y_%H%M')

    context_filename = f"{client_name}_Question_Context{timestamp}.txt"
    context_path = f"panelitix/The Big Question/Predictive Report/Question Context/{context_filename}"

    logger.info("📤 Writing question context file to Supabase: %s", context_path)
    write_supabase_file(context_path, context_content)
    logger.info("✅ Question context uploaded successfully.")

    # === Step 2: Process Logo Upload (Optional) ===
    logo_field = next((a for a in answers if a['field']['ref'] == 'c5933f0a-b7ba-49b9-8169-9e6a27a3dd2a'), None)
    logo_url = None

    if logo_field:
        raw_logo_url = logo_field.get('file_url')
        if raw_logo_url:
            try:
                ext = raw_logo_url.split('.')[-1].split('?')[0].lower()
                logo_filename = f"{client_name}_Logo_{timestamp}.{ext}"
                logo_path = f"panelitix/The Big Question/Predictive Report/Logos/{logo_filename}"

                logger.info("⬇️ Downloading logo file from: %s", raw_logo_url)
                logo_response = requests.get(raw_logo_url)
                logo_response.raise_for_status()

                write_supabase_file(logo_path, logo_response.content)
                logger.info("✅ Logo uploaded successfully.")
                logo_url = f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{logo_path}"
            except Exception as e:
                logger.warning("⚠️ Logo upload failed — skipping.")
                logger.exception(e)
        else:
            logger.info("ℹ️ Logo field present but no file_url.")
    else:
        logger.info("ℹ️ No logo field found in submission.")

    # === Final Output Payload ===
    return {
        "prompt": "client_context",
        "client": form_fields.get("26f95c88-43d4-4540-83b7-0d78e1c9535e", ""),
        "client_website_url": form_fields.get("554e54d9-4cdf-41ce-935c-b2d8c5136b56", ""),
        "client_context_url": f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{context_path}",
        "logo_url": logo_url
    }
