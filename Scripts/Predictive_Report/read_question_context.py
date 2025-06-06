import time
from datetime import datetime
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # Exponential backoff: 2, 4, 8, 16, 32, 64 seconds

def run_prompt(data):
    try:
        client = data.get("client")
        if not client:
            raise ValueError("Missing 'client' in request payload")

        # Ensure client format matches saved file name
        client_safe = client.strip().replace(" ", "_")
        date_str = datetime.utcnow().strftime("%d-%m-%Y")
        supabase_path = f"Predictive_Report/Question_Context/{client_safe}_question_context_{date_str}.txt"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.info(f"Attempting to read Supabase file: {supabase_path} (Attempt {retries + 1})")
                content = read_supabase_file(supabase_path)
                logger.info(f"✅ File retrieved successfully from Supabase for client: {client_safe}")

                return {
                    "status": "success",
                    "client": client,
                    "question_context": content.strip()
                }

            except Exception as e:
                logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        logger.error(f"❌ Max retries exceeded. File not found for client: {client_safe}")
        return {
            "status": "error",
            "client": client,
            "message": "Question context file not yet available. Try again later."
        }

    except Exception as e:
        logger.exception("Unhandled error in read_question_context")
        return {
            "status": "error",
            "message": f"Unhandled server error during question context read: {str(e)}"
        }
