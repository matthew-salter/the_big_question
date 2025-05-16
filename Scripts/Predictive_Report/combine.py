import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def clean_text_block(text: str) -> str:
    """
    Removes blank lines and leading/trailing whitespace on each line.
    """
    lines = text.strip().splitlines()
    cleaned = [line.strip() for line in lines if line.strip()]
    return '\n'.join(cleaned)

def run_prompt(data: dict) -> dict:
    try:
        run_id = data.get("run_id")
        if not run_id:
            return {"error": "Missing run_id"}

        # Extract all 4 inputs
        blocks = {
            "prompt_1_thinking": data.get("prompt_1_thinking", ""),
            "prompt_2_section_assets": data.get("prompt_2_section_assets", ""),
            "prompt_3_report_assets": data.get("prompt_3_report_assets", ""),
            "prompt_4_tables": data.get("prompt_4_tables", "")
        }

        # Clean all blocks
        cleaned_blocks = {
            key: clean_text_block(value)
            for key, value in blocks.items()
        }

        # Combine them into one output string (you can format this differently later)
        output = "\n\n".join([
            f"=== {key.upper()} ===\n{value}"
            for key, value in cleaned_blocks.items()
        ])

        # Write to Supabase
        path = f"The_Big_Question/Pedictive_Report/Ai_Responses/Combine/{run_id}.txt"
        write_supabase_file(path, output)

        logger.info(f"✅ Combined output written to {path}")
        return {"status": "success", "path": path}

    except Exception as e:
        logger.exception("❌ Failed to process combine step")
        return {"status": "error", "message": str(e)}
