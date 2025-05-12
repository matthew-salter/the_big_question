import time
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # 2, 4, 8, 16, 32, 64 seconds

def flatten_json_like_text(text: str) -> str:
    """
    Converts a JSON-style string into readable block text,
    removing JSON artefacts (quotes, brackets, commas) but preserving key: value pairs.
    """
    lines = text.strip().splitlines()
    result = []
    indent_level = 0

    for line in lines:
        clean = line.strip()

        # Skip markdown or empty lines
        if clean.startswith("```") or not clean:
            continue

        # Remove array brackets and trailing commas
        clean = clean.replace("[", "").replace("]", "").rstrip(",")
        clean = clean.replace('",', '').replace('",', '')
        clean = clean.strip('"')  # Remove enclosing quotes

        # Decrease indent level
        if clean.startswith("}") or clean.startswith("},"):
            indent_level = max(indent_level - 1, 0)
            continue

        # Handle nested block
        if clean.endswith("{") or clean.endswith("{,"):
            key = clean.split(":", 1)[0].strip().strip('"')
            result.append("  " * indent_level + f"{key}:")
            indent_level += 1
        elif ":" in clean:
            key, value = clean.split(":", 1)
            key = key.strip().strip('"')
            value = value.strip().strip('"')
            result.append("  " * indent_level + f"{key}: {value}")
        else:
            result.append("  " * indent_level + clean)

    return "\n".join(result)

def run_prompt(data):
    try:
        run_id = data.get("run_id")
        if not run_id:
            raise ValueError("Missing run_id in request payload")

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Report_Image_Prompts/{run_id}.txt"

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
                    "report_image_prompts": flattened
                }

            except Exception as e:
                logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        logger.error(f"❌ Max retries exceeded. File not found for run_id: {run_id}")
        return {
            "status": "error",
            "run_id": run_id,
            "message": "Report Image Prompts file not yet available. Try again later."
        }

    except Exception as e:
        logger.exception("Unhandled error in read_report_image_prompts")
        return {
            "status": "error",
            "message": f"Unhandled server error: {str(e)}"
        }
