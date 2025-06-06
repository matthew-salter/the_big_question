import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file

# Load American to British dictionary from external file
def load_american_to_british_dict(filepath):
    mapping = {}
    with open(filepath, 'r', encoding='utf-8') as file:
        for line in file:
            if ':' in line:
                us, uk = line.strip().rstrip(',').split(':')
                us = us.strip().strip('"')
                uk = uk.strip().strip('"')
                mapping[us] = uk
    return mapping

american_to_british = load_american_to_british_dict("Prompts/American_to_British/american_to_british.txt")

# Case formatting
def to_paragraph_case(text):
    paragraphs = text.split('\n')
    return '\n'.join([p[:1].upper() + p[1:] if p else '' for p in paragraphs])

# American to British conversion
def convert_to_british_english(text):
    def replace_match(match):
        us_word = match.group(0)
        lower_us = us_word.lower()
        if lower_us in american_to_british:
            british = american_to_british[lower_us]
            if us_word.isupper():
                return british.upper()
            elif us_word[0].isupper():
                return british.capitalize()
            else:
                return british
        return us_word

    pattern = r'\b(' + '|'.join(re.escape(word) for word in american_to_british.keys()) + r')\b'
    return re.sub(pattern, replace_match, text, flags=re.IGNORECASE)

def format_image_prompts_block(block):
    lines = block.strip().split('\n')
    output_lines = []

    for line in lines:
        if not line.strip():
            continue

        match = re.match(r'^([A-Z][A-Za-z0-9 \-]*?):\s*(.*)', line.strip())
        if match:
            key, value = match.groups()
            cleaned_value = convert_to_british_english(value.strip())
            paragraphed = to_paragraph_case(cleaned_value)
            output_lines.append(f"{key.strip()}: {paragraphed}")
            output_lines.append("")  # line break after each

    return '\n'.join(output_lines).strip()

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        report_block = data.get("report_image_prompts", "")
        section_block = data.get("section_image_prompts", "")

        # Format both blocks
        formatted_report = format_image_prompts_block(report_block)
        formatted_section = format_image_prompts_block(section_block)

        combined_output = f"{formatted_report}\n\n{formatted_section}".strip()

        supabase_path = f"Predictive_Report/Ai_Responses/Format_Image_Prompts/{run_id}.txt"
        write_supabase_file(supabase_path, combined_output)
        logger.info(f"✅ Formatted image prompt content written to Supabase: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved file from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read back from Supabase immediately: {read_error}")
            content = combined_output  # fallback

        return {
            "status": "success",
            "run_id": run_id,
            "formatted_content": content.strip()
        }

    except Exception as e:
        logger.exception("❌ Error in format_image_prompts script")
        return {
            "status": "error",
            "message": str(e)
        }
