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

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())

        raw_combine = data.get("combine", "")
        cleaned_combine = convert_to_british_english(raw_combine.strip())

        client = data.get("client", "").strip()
        website = data.get("client_website_url", "").strip()
        context = convert_to_british_english(data.get("client_context", "").strip())
        question = data.get("main_question", "").strip()
        report = data.get("report", "").strip()
        year = data.get("year", "").strip()

        header = f"Client:\n{client}\n\nWebsite:\n{website}\n\nAbout Client:\n{context}\n\nMain Question:\n{question}\n\nReport:\n{report}\n\nYear:\n{year}"

        final_text = f"{header}\n\n{cleaned_combine}"

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/New_Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_text)
        logger.info(f"✅ Written raw + header output to Supabase: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved raw output from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read file back from Supabase immediately: {read_error}")
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
