import time
import json
from logger import logger
from Engine.Files.read_supabase_file import read_supabase_file

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 2  # 2, 4, 8, 16, 32, 64 seconds

def flatten_json_like_text(text: str) -> str:
    lines = text.strip().splitlines()
    result = []
    indent_level = 0

    for line in lines:
        clean_line = line.strip()
        if clean_line.startswith("```"):
            continue
        if clean_line.startswith("}") or clean_line.startswith("},"):
            indent_level = max(indent_level - 1, 0)
            continue
        if clean_line.endswith("{") or clean_line.endswith("{,"):
            key = clean_line.split(":", 1)[0].strip().strip('"')
            result.append("  " * indent_level + f"{key}:")
            indent_level += 1
        elif ":" in clean_line:
            key, value = line.split(":", 1)
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

        supabase_path = f"Elasticity/Ai_Responses/Prompt_1_Elasticity/{run_id}.txt"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.info(f"Attempting to read Supabase file: {supabase_path} (Attempt {retries + 1})")
                raw_content = read_supabase_file(supabase_path)
                logger.info(f"✅ File retrieved successfully from Supabase for run_id: {run_id}")

                # Flatten for readability
                flattened = flatten_json_like_text(raw_content).replace("{:", "")

                # Extract numeric elasticity values from the JSON structure
                try:
                    parsed_json = json.loads(raw_content)
                    supply_es = parsed_json.get("Supply", {}).get("Supply Elasticity", "").strip()
                    demand_ed = parsed_json.get("Demand", {}).get("Demand Elasticity", "").strip()
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse elasticity values from raw JSON: {e}")
                    supply_es = ""
                    demand_ed = ""

                return {
                    "status": "success",
                    "run_id": run_id,
                    "prompt_1_elasticicty": flattened,
                    "Supply Elasticity (Es)": supply_es,
                    "Demand Elasticity (Ed)": demand_ed
                }

            except Exception as e:
                logger.warning(f"File not yet available. Retry {retries + 1} of {MAX_RETRIES}. Error: {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS * (2 ** retries))
                retries += 1

        return {
            "status": "error",
            "run_id": run_id,
            "message": "Prompt 1 Elasticity file not yet available. Try again later."
        }

    except Exception as e:
        logger.exception("Unhandled error in read_prompt_1_elasticity")
        return {
            "status": "error",
            "message": f"Unhandled server error: {str(e)}"
        }

    except Exception as e:
        logger.exception("Unhandled error in read_prompt_1_elasticity")
        return {
            "status": "error",
            "message": f"Unhandled server error: {str(e)}"
        }

            "status": "error",
            "message": f"Unhandled server error: {str(e)}"
        }
