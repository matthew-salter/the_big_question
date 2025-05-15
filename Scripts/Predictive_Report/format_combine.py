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

# Keys that should have a blank line before (outside block context)
linebreak_keys = {
    "Report Title", "Report Sub-Title", "Executive Summary", "Key Findings", "Call to Action",
    "Report Change Title", "Report Change", "Report Table", "Section Title", "Section Header", "Section Sub-Header",
    "Section Theme", "Section Summary", "Section Makeup", "Section Statistic", "Section Recommendation",
    "Section Tables", "Section Related Article Date", "Section Related Article Summary", "Section Related Article Relevance",
    "Section Related Article Source", "Sub-Sections", "Sub-Section Title", "Sub-Section Header", "Sub-Section Sub-Header",
    "Sub-Section Summary", "Sub-Section Makeup", "Sub-Section Related Article Title", "Sub-Section Related Article Date",
    "Sub-Section Related Article Summary", "Sub-Section Related Article Relevance"
}

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

        # --- Report Table Block ---
        if line.startswith("Report Table:"):
            if not in_report_table and not in_section_table:
                formatted_lines.append("")
            in_report_table = True
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

        # --- Section Tables Block ---
        if line.startswith("Section Tables:"):
            if not in_report_table and not in_section_table:
                formatted_lines.append("")
            in_section_table = True
            formatted_lines.append(line)
            i += 1
            continue

        if in_section_table and line.startswith("Section Related Article Title:"):
            in_section_table = False
            formatted_lines.append(line)
            i += 1
            continue

        if in_section_table:
            if line.startswith("Sub-Section Title:"):
                formatted_lines.append(line)
                if i+3 < len(lines):
                    makeup = lines[i+1]
                    change = lines[i+2]
                    effect = lines[i+3]
                    if (
                        makeup.startswith("Sub-Section Makeup:") and
                        change.startswith("Sub-Section Change:") and
                        effect.startswith("Sub-Section Effect:")
                    ):
                        summary = f"Sub-Section Makeup: {makeup.split(':',1)[1].strip()} | Sub-Section Change: {change.split(':',1)[1].strip()} | Sub-Section Effect: {effect.split(':',1)[1].strip()}"
                        formatted_lines.append(summary)
                        formatted_lines.append("")
                        i += 4
                        continue
            i += 1
            continue

        # --- Outside All Blocks: Combine grouped metrics ---
        if (
            i+2 < len(lines) and
            lines[i].startswith("Section Makeup:") and
            lines[i+1].startswith("Section Change:") and
            lines[i+2].startswith("Section Effect:")
        ):
            summary = f"{lines[i]} | {lines[i+1]} | {lines[i+2]}"
            formatted_lines.append(summary)
            formatted_lines.append("")
            i += 3
            continue

        if (
            i+2 < len(lines) and
            lines[i].startswith("Sub-Section Makeup:") and
            lines[i+1].startswith("Sub-Section Change:") and
            lines[i+2].startswith("Sub-Section Effect:")
        ):
            summary = f"{lines[i]} | {lines[i+1]} | {lines[i+2]}"
            formatted_lines.append(summary)
            formatted_lines.append("")
            i += 3
            continue

        # --- Default Formatting ---
        match = re.match(r'^([A-Z][A-Za-z \-]*?):(.*)', line)
        if match:
            key, value = match.groups()
            key = key.strip()
            value = value.strip()
            formatter = asset_formatters.get(key, lambda x: x)
            formatted = formatter(value)

            if not in_report_table and not in_section_table and key in linebreak_keys:
                if formatted_lines and formatted_lines[-1] != "":
                    formatted_lines.append("")  # Add a blank line

            formatted_lines.append(f"{key}:{formatted}")
        else:
            formatted_lines.append(line)

        i += 1

    # Catch trailing report block
    if in_report_table and current_group:
        summary = f"{current_group.get('Section Makeup', '')} | {current_group.get('Section Change', '')} | {current_group.get('Section Effect', '')}"
        formatted_lines.append(summary)
        formatted_lines.append("")

    final_text = '\n'.join(formatted_lines)
    final_text = re.sub(r':(?!\s)', ': ', final_text)  # Ensure there's a space after each colon
    final_text = re.sub(r':\s{2,}', ': ', final_text)  # Remove any double spaces after colon
    return final_text

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        formatted_text = format_text(raw_text)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_text)
        logger.info(f"✅ Cleaned & formatted output written to Supabase: {supabase_path}")

        # Immediately read back the file from Supabase
        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved formatted content from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read file back from Supabase immediately: {read_error}")
            content = formatted_text  # Fallback to in-memory result

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
