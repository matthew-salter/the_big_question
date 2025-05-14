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
    return '\n'.join([to_sentence_case(p.strip()) for p in paragraphs if p.strip()])

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

# Asset formatting map
asset_formatters = {
    "Report Title": to_title_case,
    "Report Sub-Title": to_title_case,
    "Executive Summary": to_paragraph_case,
    "Key Findings": format_bullet_points,
    "Call to Action": to_sentence_case,
    "Report Change Title": to_title_case,
    "Report Change": to_title_case,
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
    "Section Related Article Date": to_title_case,
    "Section Related Article Summary": to_paragraph_case,
    "Section Related Article Relevance": to_paragraph_case,
    "Section Related Article Source": to_title_case,
    "Sub-Section Title": to_title_case,
    "Sub-Section Header": to_title_case,
    "Sub-Section Sub-Header": to_title_case,
    "Sub-Section Summary": to_paragraph_case,
    "Sub-Section Statistic": to_sentence_case,
    "Sub-Section Related Article Title": to_title_case,
    "Sub-Section Related Article Date": to_title_case,
    "Sub-Section Related Article Summary": to_paragraph_case,
    "Sub-Section Related Article Relevance": to_paragraph_case,
    "Sub-Section Related Article Source": to_title_case,
    "Conclusion": to_paragraph_case,
    "Recommendations": format_bullet_points,
}

def format_text(text):
    text = re.sub(r'[\t\r]+', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = convert_to_british_english(text)

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    output_lines = []

    block = 1
    section = 0
    section_item = 0
    subsection = 0
    sub_item = 0
    sub_group = 0
    in_report_table = False
    in_sections = False
    in_tables = False

    for line in lines:
        match = re.match(r'^([A-Z][A-Za-z \-]*?):(.*)', line)
        if match:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()

            # format value
            value = asset_formatters.get(key, lambda x: x)(value)

            if key == "Report Table":
                block += 1
                output_lines.append(f"{block} {key}:{value}")
                section = 1
                in_report_table = True
                continue

            if key == "Sections":
                block += 1
                output_lines.append(f"{block} {key}:{value}")
                section = 1
                in_sections = True
                continue

            if key == "Section Title" and in_report_table:
                section_item = 1
                output_lines.append(f"{block}.{section}.{section_item} {key}:{value}")
                continue

            if key in ["Section Makeup", "Section Change", "Section Effect"] and in_report_table:
                section_item += 1
                output_lines.append(f"{block}.{section}.{section_item} {key}:{value}")
                continue

            if key == "Section Title" and in_sections:
                section_item = 1
                output_lines.append(f"{block}.{section}.{section_item} {key}:{value}")
                continue

            if key.startswith("Section") and in_sections:
                section_item += 1
                output_lines.append(f"{block}.{section}.{section_item} {key}:{value}")
                continue

            if key == "Section Tables":
                in_tables = True
                sub_group = 1
                output_lines.append(f"{block}.{section}.{section_item} {key}:{value}")
                continue

            if key == "Sub-Section Title" and in_tables:
                sub_item = 1
                output_lines.append(f"{block}.{section}.{section_item}.{sub_group}.{sub_item} {key}:{value}")
                continue

            if key.startswith("Sub-Section") and in_tables:
                sub_item += 1
                output_lines.append(f"{block}.{section}.{section_item}.{sub_group}.{sub_item} {key}:{value}")
                if key == "Sub-Section Effect":
                    sub_group += 1
                continue

            if key.startswith("Sub-Section"):
                subsection += 1
                output_lines.append(f"{block}.{section}.{subsection} {key}:{value}")
                continue

            output_lines.append(f"{block} {key}:{value}")
            block += 1
        else:
            output_lines.append(line)

    return '\n'.join(output_lines)

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_text = format_text(raw_text)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_text)
        logger.info(f"\u2705 Cleaned & numbered output written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": formatted_text}

    except Exception as e:
        logger.exception("\u274C Error in formatting script")
        return {"status": "error", "message": str(e)}
