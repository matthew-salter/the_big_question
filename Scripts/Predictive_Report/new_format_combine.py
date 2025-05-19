import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file

# Load American to British dictionary
def load_american_to_british_dict(filepath):
    mapping = {}
    with open(filepath, 'r', encoding='utf-8') as file:
        for line in file:
            if ':' in line:
                us, uk = line.strip().rstrip(',').split(':')
                mapping[us.strip().strip('"')] = uk.strip().strip('"')
    return mapping

american_to_british = load_american_to_british_dict("Prompts/American_to_British/american_to_british.txt")

# Convert words to British English
def convert_to_british_english(text):
    def replace_match(match):
        us_word = match.group(0)
        lowercase_us = us_word.lower()
        if lowercase_us in american_to_british:
            british = american_to_british[lowercase_us]
            if us_word.isupper():
                return british.upper()
            elif us_word[0].isupper():
                return british.capitalize()
            else:
                return british
        return us_word

    pattern = r'\b(' + '|'.join(re.escape(word) for word in american_to_british.keys()) + r')\b'
    return re.sub(pattern, replace_match, text, flags=re.IGNORECASE)

# Indent block content
def indent_block_content(text, start_marker, end_marker):
    pattern = re.compile(
        rf'({re.escape(start_marker)}\n)(.*?)(?=\n{re.escape(end_marker)})',
        re.DOTALL
    )

    def replacer(match):
        header = match.group(1)
        block_content = match.group(2)
        indented = '\n'.join(['\t' + line if line.strip() else '' for line in block_content.split('\n')])
        return header + indented

    return re.sub(pattern, replacer, text)

# Reformat asset blocks
def reformat_assets(text):
    inline_keys = {
        "Section #:", "Section Makeup:", "Section Change:", "Section Effect:",
        "Sub-Section #:", "Sub-Section Makeup:", "Sub-Section Change:", "Sub-Section Effect:"
    }

    lines = text.split('\n')
    formatted_lines = []
    inside_table_block = False
    buffer = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect start/end of Report or Section Tables
        if stripped in {"Report Table:", "Section Tables:"}:
            inside_table_block = True
        elif stripped.startswith("Section #:") or stripped.startswith("Sub-Section #:"):
            inside_table_block = False

        # Skip changes inside table blocks
        if inside_table_block or not stripped:
            formatted_lines.append(line)
            continue

        # Handle grouped Section Makeup + Change + Effect
        if stripped.startswith("Section Makeup:"):
            prev_line = formatted_lines[-1] if formatted_lines else ""
            if prev_line.strip() != "":
                formatted_lines.append("")
            formatted_lines.append(line.strip() + " | " + lines[i + 1].strip() + " | " + lines[i + 2].strip())
            continue  # Skip next two lines

        if stripped.startswith("Sub-Section Makeup:"):
            prev_line = formatted_lines[-1] if formatted_lines else ""
            if prev_line.strip() != "":
                formatted_lines.append("")
            formatted_lines.append(line.strip() + " | " + lines[i + 1].strip() + " | " + lines[i + 2].strip())
            continue  # Skip next two lines

        # Break inline values unless key is in exception list
        if ':' in line:
            key, value = line.split(':', 1)
            full_key = f"{key.strip()}:"
            if full_key in inline_keys:
                formatted_lines.append(line)
            else:
                formatted_lines.append(f"\n{full_key}")
                if value.strip():
                    formatted_lines.append(value.strip())
        else:
            formatted_lines.append(line)

    return '\n'.join(formatted_lines)

# Format full report
def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())

        # Extract fields
        client = data.get("client", "").strip()
        website = data.get("client_website_url", "").strip()
        context = data.get("client_context", "").strip()
        question = data.get("main_question", "").strip()
        report = data.get("report", "").strip()
        year = data.get("year", "").strip()
        combine = data.get("combine", "").strip()

        if not combine:
            raise ValueError("Missing 'combine' content in input data.")

        # Step 1: Convert to British English
        combine_text = convert_to_british_english(combine)

        # Step 2: Isolate and indent Report Table and Section Table blocks
        combine_text = indent_block_content(combine_text, "Report Table:", "Section #:")
        combine_text = indent_block_content(combine_text, "Section Tables:", "Sub-Section #:")

        # Step 3: Apply line-break rules for all other assets
        combine_text = reformat_assets(combine_text)

        # Step 4: Assemble output
        header = f"""Client:
{client}

Website:
{website}

About Client:
{context}

Main Question:
{question}

Report:
{report}

Year:
{year}

"""
        final_text = f"{header}{combine_text.strip()}"

        # Write to Supabase
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/New_Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_text)
        logger.info(f"✅ New formatted file written to: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
        except Exception as e:
            logger.warning(f"⚠️ Could not read file back from Supabase: {e}")
            content = final_text

        return {
            "status": "success",
            "run_id": run_id,
            "formatted_content": content.strip()
        }

    except Exception as e:
        logger.exception("❌ Error in new_format_combine.py")
        return {
            "status": "error",
            "message": str(e)
        }
