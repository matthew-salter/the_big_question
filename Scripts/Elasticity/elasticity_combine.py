import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def deindent(text):
    return re.sub(r'(?m)^ {2,}', '', text)

def insert_additional_fields(text, client, elasticity_change, elasticity_calculation):
    # Inject Client after Report Title
    text = re.sub(r'(Report Title:.*?\n)', r'\1Client: {}\n'.format(client), text, count=1)

    # Inject Elasticity Change and Calculation after Elasticity Summary
    text = re.sub(
        r'(Elasticity Summary:.*?)\n',
        r'\1\nElasticity Change: {}\nElasticity Calculation: {}\n'.format(elasticity_change, elasticity_calculation),
        text,
        count=1
    )
    return text

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
        prompt_raw = data.get("prompt_1_elasticity", "").strip()
        client = data.get("client", "").strip()
        elasticity_change = data.get("elasticity_change", "").strip()
        elasticity_calculation = data.get("elasticity_calculation", "").strip()

        if not prompt_raw:
            raise ValueError("Missing 'prompt_1_elasticity' content in input data.")

        text = deindent(prompt_raw)
        text = insert_additional_fields(text, client, elasticity_change, elasticity_calculation)
        text = remove_section_headers(text)
        text = split_key_value_lines(text)

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
