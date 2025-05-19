import re
import uuid
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

# British English conversion
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

# Formatting map
asset_formatters = {
    "Report Title": to_title_case,
    "Report Sub-Title": to_title_case,
    "Executive Summary": to_paragraph_case,
    "Key Findings": format_bullet_points,
    "Call to Action": to_sentence_case,
    "Report Change Title": to_title_case,
    "Report Change": to_title_case,
    "Conclusion": to_paragraph_case,
    "Recommendations": format_bullet_points,
}

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("combine", "")
        client = to_title_case(data.get("client", ""))
        website = data.get("client_website_url", "").strip()
        context = to_paragraph_case(convert_to_british_english(data.get("client_context", "")))
        question = to_title_case(data.get("main_question", ""))
        report = to_title_case(data.get("report", ""))
        year = data.get("year", "").strip()

        # Format content
        raw_text = re.sub(r'[\t\r]+', '', raw_text)
        raw_text = re.sub(r'\n+', '\n', raw_text).strip()
        raw_text = convert_to_british_english(raw_text)

        lines = raw_text.split('\n')
        formatted_lines = []

        for line in lines:
            match = re.match(r'^([A-Z][A-Za-z \-]*?):\s*(.*)', line)
            if match:
                key, value = match.groups()
                formatter = asset_formatters.get(key.strip(), lambda x: x)
                formatted = formatter(value.strip())
                formatted_lines.append(f"{key}: {formatted}")
            else:
                formatted_lines.append(line)

        formatted_body = '\n'.join(formatted_lines)

        # Add header block
        header = f"Client:\n{client}\n\nWebsite:\n{website}\n\nAbout Client:\n{context}\n\nMain Question:\n{question}\n\nReport:\n{report}\n\nYear:\n{year}"
        final_text = f"{header}\n\n{formatted_body.strip()}"

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/New_Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_text)
        logger.info(f"✅ New formatted output written to Supabase: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved new formatted content from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read file back from Supabase immediately: {read_error}")
            content = final_text

        return {
            "status": "success",
            "run_id": run_id,
            "formatted_content": content.strip()
        }

    except Exception as e:
        logger.exception("❌ Error in new formatting script")
        return {
            "status": "error",
            "message": str(e)
        }
