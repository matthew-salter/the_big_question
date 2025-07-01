import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def deindent(text):
    return re.sub(r'(?m)^ {2,}', '', text)

def insert_additional_fields(text, client, elasticity_change, elasticity_calculation):
    # Insert Client after Report Title
    text = re.sub(
        r'(Report Title:.*?\n)',
        r'\1Client: {}\n'.format(client),
        text,
        count=1
    )

    # Insert Elasticity Change before Elasticity Summary
    text = re.sub(
        r'(Elasticity Summary:)',
        f"Elasticity Change: {elasticity_change}\n\n\\1",
        text,
        count=1
    )

    # Append Elasticity Calculation at the end
    text = text.rstrip() + "\n\nElasticity Calculation:\n" + elasticity_calculation + "\n"

def remove_section_headers(text):
    lines = text.splitlines()
    return '\n'.join(line for line in lines if not re.fullmatch(r'(Report|Supply|Demand|Elasticity):', line.strip()))

def split_key_value_lines(text):
    formatted = []
    for line in text.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            formatted.append(f"{key}:")
            if value:
                formatted.append(f"{value}")
            formatted.append("")  # blank line
        elif line.strip() == "":
            continue
        else:
            formatted.append(line)
            formatted.append("")
    return '\n'.join(formatted).strip()

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        prompt_raw = data.get("prompt_1_elasticity", "")
        client = data.get("client", "").strip()
        elasticity_change = data.get("elasticity_change", "").strip()
        elasticity_calculation = data.get("elasticity_calculation", "").strip()

        if not prompt_raw or not isinstance(prompt_raw, str):
            raise ValueError("Missing or invalid 'prompt_1_elasticity' content in input data.")

        # Step 1: De-indent the raw block
        text = re.sub(r'(?m)^ {2,}', '', prompt_raw.strip())

        # Step 2: Inject client + elasticity fields
        text = insert_additional_fields(text, client, elasticity_change, elasticity_calculation)

        # Step 3: Remove section headers (Report:, Supply:, etc.)
        text = remove_section_headers(text)

        # Step 4: Split keys and values onto separate lines
        text = split_key_value_lines(text)

        # Step 5: Write to Supabase
        supabase_path = f"Elasticity/Ai_Responses/Elasticity_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, text)

        logger.info(f"✅ Elasticity file written to: {supabase_path}")

        return {
            "status": "success",
            "run_id": run_id,
            "supabase_path": supabase_path,
            "formatted_content": text
        }

    except Exception as e:
        logger.exception("❌ Error in elasticity_combine.py")
        return {
            "status": "error",
            "message": str(e)
        }
