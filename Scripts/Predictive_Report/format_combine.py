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

# Formatting rules per asset
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

# Key depth mapping
key_depth = {
    "Intro": 1,
    "Report Title": 1,
    "Report Sub-Title": 1,
    "Executive Summary": 1,
    "Key Findings": 1,
    "Call to Action": 1,
    "Report Change Title": 1,
    "Report Change": 1,
    "Report Table": 1,
    "Section Title": 2,
    "Section Header": 2,
    "Section Sub-Header": 2,
    "Section Theme": 2,
    "Section Summary": 2,
    "Section Insight": 2,
    "Section Statistic": 2,
    "Section Recommendation": 2,
    "Section Tables": 2,
    "Section Related Article Title": 2,
    "Section Related Article Date": 2,
    "Section Related Article Summary": 2,
    "Section Related Article Relevance": 2,
    "Section Related Article Source": 2,
    "Sub-Section Title": 3,
    "Sub-Section Header": 3,
    "Sub-Section Sub-Header": 3,
    "Sub-Section Summary": 3,
    "Sub-Section Statistic": 3,
    "Sub-Section Related Article Title": 3,
    "Sub-Section Related Article Date": 3,
    "Sub-Section Related Article Summary": 3,
    "Sub-Section Related Article Relevance": 3,
    "Sub-Section Related Article Source": 3,
    "Sections": 1,
    "Conclusion": 1,
    "Recommendations": 1,
}

def format_text(text):
    text = re.sub(r'[\t\r]+', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = convert_to_british_english(text)

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    stack = []
    counters = []
    output_lines = []

    for line in lines:
        match = re.match(r'^([A-Z][A-Za-z \-]*?):\s*(.*)', line)
        if match:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()
            depth = key_depth.get(key, 1)

            # Adjust stack size to current depth
            while len(counters) > depth:
                counters.pop()
            if len(counters) < depth:
                counters.extend([0] * (depth - len(counters)))

            counters[-1] += 1

            block_id = '.'.join(str(c) for c in counters)
            formatted = asset_formatters.get(key, lambda x: x)(value)
            output_lines.append(f"{block_id} {key}:{formatted}")
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
        logger.info(f"\u2705 Hierarchical output written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": formatted_text}

    except Exception as e:
        logger.exception("\u274C Error in formatting script")
        return {"status": "error", "message": str(e)}
