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

    lines = text.split('\n')
    output_lines = []

    major = 0
    section = 0
    section_inner = 0
    subsection = 0
    subsection_inner = 0

    current_context = ""

    for line in lines:
        match = re.match(r'^([A-Z][A-Za-z \-]*?):(.*)', line.strip())
        if match:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()

            # Context detection and number incrementing logic
            if key == "Report Change":
                major += 1
                section = 0
                output_lines.append(f"{major} {key}:{value}")
                current_context = ""
                continue

            if key == "Report Table":
                major += 1
                section = 0
                output_lines.append(f"{major} {key}:{value}")
                current_context = "report_table"
                continue

            if key == "Sections":
                major += 1
                section = 0
                output_lines.append(f"{major} {key}:{value}")
                current_context = "sections"
                continue

            if current_context == "report_table":
                if key == "Section Title":
                    section += 1
                    section_inner = 1
                output_lines.append(f"{major}.{section}.{section_inner} {key}:{value}")
                section_inner += 1
                continue

            if current_context == "sections":
                if key == "Section Title":
                    section += 1
                    section_inner = 1
                elif key == "Sub-Section Title":
                    subsection += 1
                    subsection_inner = 1
                    output_lines.append(f"{major}.{section}.9.{subsection}.{subsection_inner} {key}:{value}")
                    subsection_inner += 1
                    continue
                elif key.startswith("Sub-Section"):
                    output_lines.append(f"{major}.{section}.9.{subsection}.{subsection_inner} {key}:{value}")
                    subsection_inner += 1
                    continue
                output_lines.append(f"{major}.{section}.{section_inner} {key}:{value}")
                section_inner += 1
                continue

            # Default major block (Intro etc.)
            major += 1
            output_lines.append(f"{major} {key}:{value}")

        else:
            if line.strip():
                output_lines.append(line.strip())

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

