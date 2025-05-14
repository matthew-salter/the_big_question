import uuid
import re
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

def clean_and_format_text(text):
    # Step 1: Strip tabs, carriage returns, and blank lines
    text = re.sub(r'[\t\r]+', '', text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)

    # Step 2: Convert American to British spelling
    text = convert_to_british_english(text)

    # Step 3: Apply formatting
    formatted_lines = []
    for line in text.split('\n'):
        if re.match(r'^- ', line):
            formatted_lines.append(format_bullet_points(line))
        elif re.match(r'^[A-Z][A-Za-z\- ]*:', line):
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key in {"Executive Summary", "Section Summary", "Section Related Article Summary", "Section Related Article Relevance", "Conclusion"}:
                value = to_paragraph_case(value)
            elif key in {"Key Findings", "Recommendations"}:
                value = format_bullet_points(value)
            elif key in {"Call to Action", "Section Insight", "Section Statistic", "Section Recommendation", "Sub-Section Statistic"}:
                value = to_sentence_case(value)
            else:
                value = to_title_case(value)
            formatted_lines.append(f"{key}:{value}")
        else:
            formatted_lines.append(to_sentence_case(line))

    return '\n'.join(formatted_lines)

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_text = clean_and_format_text(raw_text)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_text)
        logger.info(f"\u2705 Cleaned & formatted output written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": formatted_text}

    except Exception as e:
        logger.exception("\u274C Error in formatting script")
        return {"status": "error", "message": str(e)}
