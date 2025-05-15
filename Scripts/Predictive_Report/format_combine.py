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

linebreak_keys = {
    "Report Title", "Report Sub-Title", "Executive Summary", "Key Findings", "Call to Action",
    "Report Change Title", "Report Change", "Report Table", "Section Title", "Section Header", "Section Sub-Header",
    "Section Theme", "Section Summary", "Section Makeup", "Section Statistic", "Section Recommendation",
    "Section Tables", "Section Related Article Date", "Section Related Article Summary", "Section Related Article Relevance",
    "Section Related Article Source", "Sub-Sections", "Sub-Section Title", "Sub-Section Header", "Sub-Section Sub-Header",
    "Sub-Section Summary", "Sub-Section Makeup", "Sub-Section Related Article Title", "Sub-Section Related Article Date",
    "Sub-Section Related Article Summary", "Sub-Section Related Article Relevance"
}

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_body = convert_to_british_english(raw_text)
        formatted_body = re.sub(r'\bIntro:\s*', '', formatted_body)
        formatted_body = re.sub(r'\bSections:\s*', '', formatted_body)
        formatted_body = re.sub(r'\bOutro:\s*', '', formatted_body)

        # Add header block
        client = to_title_case(data.get("client", ""))
        website = data.get("client_website_url", "").strip()
        context = to_paragraph_case(convert_to_british_english(data.get("client_context", "")))
        question = to_title_case(data.get("main_question", ""))
        report = to_title_case(data.get("report", ""))
        header = f"Client: {client}\n\nWebsite: {website}\n\nAbout Client: {context}\n\nMain Question: {question}\n\nReport: {report}\n"

        lines = [line.strip() for line in formatted_body.split('\n') if line.strip()]
        final_lines = []
        in_report_table = False
        in_section_table = False
        current_group = {}

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith("Report Table:"):
                in_report_table = True
            elif line.startswith("Sections:"):
                in_report_table = False
            elif line.startswith("Section Tables:"):
                in_section_table = True
            elif line.startswith("Section Related Article Title:"):
                in_section_table = False

            divider = None
            if not in_report_table and not in_section_table:
                if line.startswith("Report Title:"):
                    divider = "---------"
                elif line.startswith("Section Title:") or line.startswith("Conclusion:"):
                    divider = "------"
                elif line.startswith("Sub-Section Title:") or line.startswith("Sub-Sub-Section Title:"):
                    divider = "---"

            if divider:
                final_lines.append(divider)
                final_lines.append("")

            final_lines.append(line)
            i += 1

        final_text = header + "\n\n" + "\n".join(final_lines).strip()

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_text)
        logger.info(f"✅ Cleaned & formatted output written to Supabase: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved formatted content from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read file back from Supabase immediately: {read_error}")
            content = final_text

        return {
            "status": "success",
            "run_id": run_id,
            "formatted_content": content.strip()
        }

    except Exception as e:
        logger.exception("❌ Error in formatting script")
        return {
            "status": "error",
            "message": str(e)
        }
