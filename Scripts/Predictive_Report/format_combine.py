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

# Add metadata formatter
def format_metadata_block(data):
    client = to_title_case(convert_to_british_english(data.get("client", "").strip()))
    website = data.get("client_website_url", "").strip()
    context = to_paragraph_case(convert_to_british_english(data.get("client_context", "").strip()))
    question = to_title_case(convert_to_british_english(data.get("main_question", "").strip()))
    report = to_title_case(convert_to_british_english(data.get("report", "").strip()))

    return "\n".join([
        f"Client: {client}",
        f"Website: {website}",
        f"About Client: {context}",
        f"Main Question: {question}",
        f"Report: {report}",
        ""
    ])

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_text = format_text(raw_text)

        # Apply intro/sections/outro removal
        formatted_text = re.sub(r'\bIntro:\s*', '', formatted_text)
        formatted_text = re.sub(r'\bSections:\s*', '', formatted_text)
        formatted_text = re.sub(r'\bOutro:\s*', '', formatted_text)

        # Inject metadata block at top
        metadata_block = format_metadata_block(data)
        formatted_text = f"{metadata_block}{formatted_text}"

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_text)
        logger.info(f"\u2705 Cleaned & formatted output written to Supabase: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"\ud83d\udcc5 Retrieved formatted content from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"\u26a0\ufe0f Could not read file back from Supabase immediately: {read_error}")
            content = formatted_text

        return {
            "status": "success",
            "run_id": run_id,
            "formatted_content": content.strip()
        }

    except Exception as e:
        logger.exception("\u274c Error in formatting script")
        return {
            "status": "error",
            "message": str(e)
        }
