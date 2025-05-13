import uuid
import re
import string
from datetime import datetime
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# American to British spelling conversions
american_to_british = {
    "color": "colour", "flavor": "flavour", "humor": "humour", "labor": "labour",
    "neighbor": "neighbour", "organize": "organise", "recognize": "recognise",
    "emphasize": "emphasise", "theater": "theatre", "analyze": "analyse", "defense": "defence",
    "traveling": "travelling", "counselor": "counsellor", "favorite": "favourite",
    "center": "centre", "apologize": "apologise", "catalog": "catalogue", "dialog": "dialogue",
    "meter": "metre", "liter": "litre", "gray": "grey", "mold": "mould", "plow": "plough",
    "pajamas": "pyjamas", "skeptic": "sceptic", "tire": "tyre", "aluminum": "aluminium",
    "jewelry": "jewellery", "fulfill": "fulfil", "program": "programme", "cozy": "cosy",
    "sulfur": "sulphur"
}

# Formatting functions
def convert_to_british_english(text):
    def replace_match(match):
        us_word = match.group(0)
        lowercase_us = us_word.lower()
        if lowercase_us in american_to_british:
            british = american_to_british[lowercase_us]
            # Preserve capitalisation
            if us_word.isupper():
                return british.upper()
            elif us_word[0].isupper():
                return british.capitalize()
            else:
                return british
        return us_word  # fallback
    # Build a combined regex pattern for all US spellings
    pattern = r'\b(' + '|'.join(re.escape(word) for word in american_to_british.keys()) + r')\b'
    return re.sub(pattern, replace_match, text, flags=re.IGNORECASE)

def ensure_line_breaks(text):
    lines = text.splitlines()
    return '\n\n'.join([line.strip() for line in lines if line.strip()])

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
    lines = [line.strip().lstrip('-').strip().rstrip('.') for line in text.strip().split('\n') if line.strip()]
    return '\n'.join(lines)

def format_date(text):
    for fmt in ["%d/%m/%Y", "%m/%d/%Y"]:
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text.strip()

# Key-based formatter mapping
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

        # Build asset detection pattern
        key_pattern = r"^(\s*)(?P<key>[\w\- ]+):\n(?P<value>.*?)(?=^\s*[\w\- ]+:\n|\Z)"
        matches = re.finditer(key_pattern, raw_text, flags=re.DOTALL | re.MULTILINE)

        formatted_blocks = []

        for match in matches:
            indent = match.group(1)
            key = match.group("key").strip()
            value = match.group("value").strip()

            value = convert_to_british_english(value)
            formatter = asset_formatters.get(key, lambda x: x)
            formatted_value = ensure_line_breaks(formatter(value))

            # Calculate indentation level
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
        logger.info(f"✅ Formatted content written to Supabase: {supabase_path}")

        return {"status": "success", "run_id": run_id, "formatted_content": final_output}

    except Exception as e:
        logger.exception("❌ Error in formatting script")
        return {"status": "error", "message": str(e)}
