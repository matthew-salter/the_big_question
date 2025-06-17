import time
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # 2, 4, 8, 16, 32, 64 seconds

def flatten_json_like_text(text: str) -> str:
    """
    Converts a JSON-style string into a readable, indented block text,
    stripping ``` wrappers and trailing quotes.
    """
    lines = text.strip().splitlines()
    result = []
    indent_level = 0

    for line in lines:
        clean_line = line.strip()

        # Skip markdown block markers
        if clean_line.startswith("```"):
            continue

        # Decrease indent after closing brace
        if clean_line.startswith("}") or clean_line.startswith("},"):
            indent_level = max(indent_level - 1, 0)
            continue

        # Nested object
        if clean_line.endswith("{") or clean_line.endswith("{,"):
            key = clean_line.split(":", 1)[0].strip().strip('"')
            result.append("  " * indent_level + f"{key}:")
            indent_level += 1
        elif ":" in clean_line:
            key, value = clean_line.split(":", 1)
            key = key.strip().strip('"')
            value = value.strip().strip('"').rstrip(",").rstrip('"')
            result.append("  " * indent_level + f"{key}: {value}")
        else:
            result.append("  " * indent_level + clean_line)

    return "\n".join(result)

def run_prompt(data):
    try:
        run_id = data.get("run_id")
        if not run_id:
            raise ValueError("Missing run_id in request payload")

        supabase_path = f"Predictive_Report/Ai_Responses/Change_Effect_Maths/{run_id}.txt"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.info(f"Attempting to read Supabase file: {supabase_path} (Attempt {retries + 1})")
                content = read_supabase_file(supabase_path)
                logger.info(f"✅ File retrieved successfully from Supabase for run_id: {run_id}")

                flattened = flatten_json_like_text(content).replace("{:", "")

                return {
                    "status": "success",
                    "run_id": run_id,
                    "change_effect_maths": flattened
                }

            except Exception as e:
                logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        logger.error(f"❌ Max retries exceeded. File not found for run_id: {run_id}")
        return {
            "status": "error",
            "run_id": run_id,
            "message": "Change Effect Maths file not yet available. Try again later."
        }

    except Exception as e:
        logger.exception("Unhandled error in read_prompt_1_thinking")
        return {
            "status": "error",
            "message": f"Unhandled server error: {str(e)}"
        }
