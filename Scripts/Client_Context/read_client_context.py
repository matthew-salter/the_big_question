import time
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # Exponential backoff: 2, 4, 8, 16, 32, 64 seconds

def run_prompt(data):
    try:
        run_id = data.get("run_id")
        if not run_id:
            raise ValueError("Missing run_id in request payload")

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Client_Context/{run_id}.txt"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.info(f"Attempting to read Supabase file: {supabase_path} (Attempt {retries + 1})")
                content = read_supabase_file(supabase_path)
                logger.info(f"✅ File retrieved successfully from Supabase for run_id: {run_id}")
                
                return {
                    "status": "success",
                    "run_id": run_id,
                    "client_context": content.strip()
                }

            except Exception as e:
                logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        logger.error(f"❌ Max retries exceeded. File not found for run_id: {run_id}")
        return {
            "status": "error",
            "run_id": run_id,
            "message": "Client context file not yet available. Try again later."
        }

    except Exception as e:
        logger.exception("Unhandled error in read_client_context")
        return {
            "status": "error",
            "message": f"Unhandled server error during client context read: {str(e)}"
        }
