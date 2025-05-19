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

# Formatting maps
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
    "Sub-Section Makeup": to_sentence_case,
    "Sub-Section Change": to_sentence_case,
    "Sub-Section Effect": to_sentence_case,
    "Sub-Section Statistic": to_sentence_case,
    "Sub-Section Related Article Title": to_title_case,
    "Sub-Section Related Article Date": to_title_case,
    "Sub-Section Related Article Summary": to_paragraph_case,
    "Sub-Section Related Article Relevance": to_paragraph_case,
    "Sub-Section Related Article Source": to_title_case,
    "Conclusion": to_paragraph_case,
    "Recommendations": format_bullet_points,
}

linebreak_keys = set(asset_formatters.keys())


def format_text(text):
    text = re.sub(r'[\t\r]+', '', text)
    text = re.sub(r'\n+', '\n', text).strip()
    text = convert_to_british_english(text)

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    formatted_lines = []

    in_report_table = False
    in_section_table = False
    current_group = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("Report Table:"):
            in_report_table = True
            formatted_lines.append("")
            formatted_lines.append("Report Table:")
            i += 1
            continue

        if in_report_table and line.startswith("Sections:"):
            if current_group:
                summary = f"{current_group.get('Section Makeup', '')} | {current_group.get('Section Change', '')} | {current_group.get('Section Effect', '')}"
                formatted_lines.append(summary)
                formatted_lines.append("")
                current_group = {}
            in_report_table = False
            formatted_lines.append("Sections:")
            i += 1
            continue

        if in_report_table:
            if line.startswith("Section Title:"):
                if current_group:
                    summary = f"{current_group.get('Section Makeup', '')} | {current_group.get('Section Change', '')} | {current_group.get('Section Effect', '')}"
                    formatted_lines.append(summary)
                    formatted_lines.append("")
                    current_group = {}
                formatted_lines.append(line)
            elif line.startswith("Section Makeup:"):
                current_group["Section Makeup"] = line
            elif line.startswith("Section Change:"):
                current_group["Section Change"] = line
            elif line.startswith("Section Effect:"):
                current_group["Section Effect"] = line
            else:
                formatted_lines.append(line)
            i += 1
            continue

        if line.startswith("Section Tables:"):
            in_section_table = True
            formatted_lines.append("")
            formatted_lines.append(line)
            i += 1
            continue

        if in_section_table and line.startswith("Section Related Article Title:"):
            in_section_table = False
            formatted_lines.append(line)
            i += 1
            continue

        if in_section_table:
            formatted_lines.append(line)
            i += 1
            continue

        match = re.match(r'^([A-Z][A-Za-z \-]*?):(.*)', line)
        if match and not in_report_table and not in_section_table:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()
            formatter = asset_formatters.get(key, lambda x: x)
            formatted = formatter(value)
            if key in linebreak_keys:
                if formatted_lines and formatted_lines[-1] != "":
                    formatted_lines.append("")
            formatted_lines.append(f"{key}:")
            if formatted:
                formatted_lines.append(formatted)
        else:
            formatted_lines.append(line)

        i += 1

    if in_report_table and current_group:
        summary = f"{current_group.get('Section Makeup', '')} | {current_group.get('Section Change', '')} | {current_group.get('Section Effect', '')}"
        formatted_lines.append(summary)
        formatted_lines.append("")

    return '\n'.join(formatted_lines)


def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_body = format_text(raw_text)
        formatted_body = re.sub(r'\bIntro:\s*', '', formatted_body)
        formatted_body = re.sub(r'\bSections:\s*', '', formatted_body)
        formatted_body = re.sub(r'\bOutro:\s*', '', formatted_body)

        client = to_title_case(data.get("client", ""))
        website = data.get("client_website_url", "").strip()
        context = to_paragraph_case(convert_to_british_english(data.get("client_context", "")))
        question = to_title_case(data.get("main_question", ""))
        report = to_title_case(data.get("report", ""))
        year = data.get("year", "").strip()

        header = f"Client:\n{client}\n\nWebsite:\n{website}\n\nAbout Client:\n{context}\n\nMain Question:\n{question}\n\nReport:\n{report}\n\nYear:\n{year}"

        final_text = f"{header}\n\n{formatted_body.strip()}"

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
