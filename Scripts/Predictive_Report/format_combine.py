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

def normalise_input_text(text):
    lines = text.splitlines()
    stripped_lines = [line.lstrip() for line in lines if line.strip()]
    return "\n".join(stripped_lines)

def insert_line_breaks_before_keys(text, keys):
    pattern = r'(^|\n)(?=({keys}):)'.format(
        keys='|'.join(re.escape(k) for k in keys)
    )
    return re.sub(pattern, r'\1\n', text)

def extract_and_format_report_table_block(text):
    pattern = r"(Report Table:\n)(.*?)(\n\w.*?:|\Z)"  # Match from Report Table to next key or EOF
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return text  # No Report Table found

    header, block, tail_marker = match.groups()
    lines = block.strip().splitlines()
    formatted = []

    for line in lines:
        # All-in-one-line format
        match_inline = re.match(
            r"^(.*?) Section Makeup: ([^ ]+) Section Change: ([^ ]+) Section Effect: ([^%]+%)", line
        )
        if match_inline:
            title, makeup, change, effect = match_inline.groups()
            formatted.append(f"Section Title: {title.strip()}")
            formatted.append(f"Section Makeup: {makeup.strip()} | Section Change: {change.strip()} | Section Effect: {effect.strip()}")
            continue

        # If not matched, check if it's a continuation or broken input
        if line.startswith("Section Title:"):
            title = line.replace("Section Title:", "").strip()
            formatted.append(f"Section Title: {title}")
        elif all(kw in line for kw in ["Section Makeup:", "Section Change:", "Section Effect:"]):
            # Handle broken line after Section Title
            makeup = re.search(r"Section Makeup: ([^ ]+)", line).group(1)
            change = re.search(r"Section Change: ([^ ]+)", line).group(1)
            effect = re.search(r"Section Effect: ([^%]+%)", line).group(1)
            formatted.append(f"Section Makeup: {makeup} | Section Change: {change} | Section Effect: {effect}")

    cleaned_block = header + "\n".join(formatted) + "\n" + tail_marker.strip()
    return text.replace(header + block + tail_marker, cleaned_block)

def format_report_table_block(block_text):
    lines = block_text.strip().splitlines()
    formatted = []

    for line in lines:
        match = re.match(
            r"^(.*?) Section Makeup: ([^ ]+) Section Change: ([^ ]+) Section Effect: ([^%]+%)", line.strip()
        )
        if match:
            title, makeup, change, effect = match.groups()
            formatted.append(f"Section Title: {title.strip()}")
            formatted.append(f"Section Makeup: {makeup.strip()} | Section Change: {change.strip()} | Section Effect: {effect.strip()}")

    return "\n".join(formatted)

def parse_key_value_blocks(text):
    blocks = []
    current_key = None
    current_value_lines = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            possible_key, possible_value = line.split(':', 1)
            key = possible_key.strip()
            if key in asset_formatters:
                if current_key:
                    blocks.append((current_key, '\n'.join(current_value_lines).strip()))
                current_key = key
                current_value_lines = [possible_value.strip()]
            else:
                current_value_lines.append(line)
        else:
            current_value_lines.append(line)

    if current_key:
        blocks.append((current_key, '\n'.join(current_value_lines).strip()))
    return blocks

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

def format_date(text):
    for fmt in ["%d/%m/%Y", "%m/%d/%Y"]:
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text.strip()

asset_formatters = {
    "Report Title": to_title_case,
    "Report Sub-Title": to_title_case,
    "Executive Summary": to_paragraph_case,
    "Key Findings": format_bullet_points,
    "Call to Action": to_sentence_case,
    "Report Change Title": to_title_case,
    "Report Table": to_title_case,
    "Section Title": to_title_case,
    "Section Header": to_title_case,
    "Section Sub-Header": to_title_case,
    "Section Theme": to_title_case,
    "Section Summary": to_paragraph_case,
    "Section Insight": to_sentence_case,
    "Section Statistic": to_sentence_case,
    "Section Recommendation": to_sentence_case,
    "Section Tables": to_title_case,
    "Section Related Article Title": to_title_case,
    "Section Related Article Date": format_date,
    "Section Related Article Summary": to_paragraph_case,
    "Section Related Article Relevance": to_paragraph_case,
    "Section Related Article Source": to_title_case,
    "Sub-Section Title": to_title_case,
    "Sub-Section Header": to_title_case,
    "Sub-Section Sub-Header": to_title_case,
    "Sub-Section Summary": to_paragraph_case,
    "Sub-Section Statistic": to_sentence_case,
    "Sub-Section Related Article Title": to_title_case,
    "Sub-Section Related Article Date": format_date,
    "Sub-Section Related Article Summary": to_paragraph_case,
    "Sub-Section Related Article Relevance": to_paragraph_case,
    "Sub-Section Related Article Source": to_title_case,
    "Conclusion": to_paragraph_case,
    "Recommendations": format_bullet_points,
}

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")

        normalised_text = normalise_input_text(raw_text)
        keys_to_break_before = list(asset_formatters.keys())
        clean_text_with_breaks = insert_line_breaks_before_keys(normalised_text, keys_to_break_before)

        # Process and format Report Table before parsing
        clean_text_with_breaks = extract_and_format_report_table_block(clean_text_with_breaks)

        raw_blocks = parse_key_value_blocks(clean_text_with_breaks)
        formatted_blocks = []

        for key, value in raw_blocks:
            value = convert_to_british_english(value)
            formatter = asset_formatters.get(key, lambda x: x)
            formatted_value = formatter(value)

            tabs = ""
            if "Sub-Section Related Article" in key:
                tabs = "\t" * 3
            elif "Sub-Section" in key:
                tabs = "\t" * 2
            elif "Section Related Article" in key:
                tabs = "\t"

            formatted_blocks.append(f"{tabs}{key}:\n{tabs}{formatted_value}")

        final_output = "\n\n".join(formatted_blocks)
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_output)
        logger.info(f"\u2705 Formatted content written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": final_output}

    except Exception as e:
        logger.exception("\u274C Error in formatting script")
        return {"status": "error", "message": str(e)}
