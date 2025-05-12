import time
import json
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # Exponential backoff: 2, 4, 8, 16, 32, 64 seconds

def flatten_json_text_block(json_text: str) -> str:
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Provided text is not valid JSON. Returning raw text.")
        return json_text

    def walk(obj, indent=0):
        lines = []
        indent_str = '  ' * indent
        if isinstance(obj, dict):
            for key, value in obj.items():
                lines.append(f"{indent_str}{key}:")
                lines.append(walk(value, indent + 1))
        elif isinstance(obj, list):
            for item in obj:
                lines.append(walk(item, indent + 1))
        else:
            lines.append(f"{indent_str}{str(obj)}")
        return "\n".join(lines)

    return walk(parsed)

def run_prompt(data):
    run_id = data.get("run_id")
    if not run_id:
        return {
            "status": "error",
            "message": "Missing run_id in request payload"
        }

    supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Prompt_1_Thinking/{run_id}.txt"

    retries = 0
    while retries < MAX_RETRIES:
        try:
            logger.info(f"Attempting to read Supabase file: {supabase_path} (Attempt {retries + 1})")
            content = read_supabase_file(supabase_path)
            logger.info(f"✅ File retrieved successfully from Supabase for run_id: {run_id}")
            logger.debug(f"✅ Text file read successful, content size: {len(content)} bytes")

            flattened = flatten_json_text_block(content.strip())

            return {
                "status": "success",
                "run_id": run_id,
                "prompt_1_thinking": flattened
            }

        except Exception as e:
            logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
            time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
            retries += 1

    logger.error(f"❌ Max retries exceeded. File not found for run_id: {run_id}")
    return {
        "status": "error",
        "run_id": run_id,
        "message": "Prompt 1 Thinking file not yet available. Try again later."
    }
