import uuid
import re
from datetime import datetime
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

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

# Text case functions
def to_title_case(text):
    exceptions = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "so", "the", "to", "up", "yet"}
    words = text.strip().split()
    return ' '.join([word.capitalize() if i == 0 or word.lower() not in exceptions else word.lower() for i, word in enumerate(words)])

def to_sentence_case(text):
    text = text.strip()
    return text[0].upper() + text[1:] if text else ""

def to_paragraph_case(text):
    paragraphs = text.split('\n')
    return '\n\n'.join([to_sentence_case(p) for p in paragraphs if p.strip()])

def format_bullet_points(text):
    lines = [line.strip().lstrip('-').strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(f"- {line}" for line in lines)

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

# Updated placeholder hierarchy — final version to be generated dynamically later
hierarchy_levels = {}

# Dynamically assign numbering to blocks as they appear

def format_text(text):
    text = re.sub(r'[\t\r]+', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = convert_to_british_english(text)

    pattern = r'(^|\n)([A-Z][A-Za-z \-]*?):'
    keys = re.findall(pattern, text)

    hierarchy = {}
    block_counter = 1
    section_counter = 1
    subsection_counter = 1
    numbering = {}

    lines = text.split('\n')
    output_lines = []
    current_key = None

    for line in lines:
        match = re.match(r'([A-Z][A-Za-z \-]*?):(.*)', line)
        if match:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()

            if key == "Section Title" and "Report Table:" in output_lines:
                block_id = f"8.{section_counter}.1"
                section_counter += 1
            elif key == "Section Title" and "Sections:" in output_lines:
                block_id = f"9.{section_counter}.1"
                section_counter += 1
            elif key.startswith("Sub-Section"):
                block_id = f"9.{section_counter - 1}.9.{subsection_counter}.1"
                subsection_counter += 1
            else:
                block_id = str(block_counter)
                block_counter += 1

            formatted_value = value  # Leave unformatted for now
            output_lines.append(f"{block_id} {key}:\n{formatted_value}")
        else:
            if line.strip():
                output_lines.append(line.strip())

    return '\n\n'.join(output_lines)

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_text = format_text(raw_text)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_text)
        logger.info(f"\u2705 Numbered output written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": formatted_text}

    except Exception as e:
        logger.exception("\u274C Error in formatting script")
        return {"status": "error", "message": str(e)}
