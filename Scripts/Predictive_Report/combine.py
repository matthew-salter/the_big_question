import uuid
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def clean_text_block(text: str) -> str:
    """
    Remove blank lines and leading/trailing whitespace.
    """
    lines = text.strip().splitlines()
    return '\n'.join(line.strip() for line in lines if line.strip())

def run_prompt(data: dict) -> dict:
    try:
        # Generate run_id if not provided
        run_id = data.get("run_id") or str(uuid.uuid4())
        data["run_id"] = run_id  # propagate it back in the response

        # Pull and clean all blocks
        blocks = {
            "prompt_1_thinking": clean_text_block(data.get("prompt_1_thinking", "")),
            "prompt_2_section_assets": clean_text_block(data.get("prompt_2_section_assets", "")),
            "prompt_3_report_assets": clean_text_block(data.get("prompt_3_report_assets", "")),
            "prompt_4_tables": clean_text_block(data.get("prompt_4_tables", ""))
        }

        # Concatenate the cleaned blocks for now — sorting can follow later
        formatted_output = "\n\n".join([
            f"=== {key.upper()} ===\n{value}"
            for key, value in blocks.items()
        ])

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_output)
        logger.info(f"✅ Combined cleaned output written to: {supabase_path}")

        return {
            "status": "success",
            "run_id": run_id,
            "path": supabase_path
        }

    except Exception as e:
        logger.exception("❌ combine.py failed")
        return {
            "status": "error",
            "message": str(e)
        }
