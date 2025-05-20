import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file

# Load American to British dictionary
def load_american_to_british_dict(filepath):
    mapping = {}
    with open(filepath, 'r', encoding='utf-8') as file:
        for line in file:
            if ':' in line:
                us, uk = line.strip().rstrip(',').split(':')
                mapping[us.strip().strip('"')] = uk.strip().strip('"')
    return mapping

american_to_british = load_american_to_british_dict("Prompts/American_to_British/american_to_british.txt")

# Case formatting helpers
def to_title_case(text):
    exceptions = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "so", "the", "to", "up", "yet"}
    def format_word(word):
        if '-' in word:
            return '-'.join(format_word(part) for part in word.split('-'))
        if word.upper() in {"UK", "EU", "US", "UN"}:
            return word.upper()
        return word.capitalize()
    words = text.strip().split()
    return ' '.join([
        format_word(word) if i == 0 or word.lower() not in exceptions else word.lower()
        for i, word in enumerate(words)
    ])

def to_sentence_case(text):
    text = text.strip()
    return text[0].upper() + text[1:] if text else ""

def to_paragraph_case(text):
    paragraphs = text.split('\n')
    return '\n'.join([to_sentence_case(p.strip()) for p in paragraphs if p.strip()])

def format_bullet_points(text):
    lines = [line.strip().lstrip('-').strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(f"- {line}" for line in lines)

# Asset formatting map
asset_formatters = {
    "Client": to_title_case,
    "Website": lambda x: x,
    "About Client": to_paragraph_case,
    "Main Question": to_title_case,
    "Report": to_title_case,
    "Year": lambda x: x,
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

# Convert to British English
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

# Reformat assets with spacing preserved before each new block except Report Table/Section Tables

def reformat_assets(text):
    inline_keys = {
        "Section #:", "Section Makeup:", "Section Change:", "Section Effect:",
        "Sub-Section #:", "Sub-Section Makeup:", "Sub-Section Change:", "Sub-Section Effect:"
    }
    lines = text.split('\n')
    formatted_lines = []
    inside_report_table = False
    inside_section_tables = False
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # --- Block scope entry ---
        if stripped == "Report Table:":
            inside_report_table = True
            inside_section_tables = False
            formatted_lines.append(stripped)
            i += 1
            continue

        if stripped == "Section Tables:":
            inside_report_table = False
            inside_section_tables = True
            formatted_lines.append(stripped)
            i += 1
            continue

        # --- Block scope exit ---
        if stripped.startswith("Section #:") or stripped.startswith("Sub-Section #:"):
            inside_report_table = False
            inside_section_tables = False

        # --- Format Report Table entries ---
        if (
            inside_report_table and
            i + 3 < len(lines) and
            stripped.startswith("Section Title:") and
            lines[i + 1].strip().startswith("Section Makeup:") and
            lines[i + 2].strip().startswith("Section Change:") and
            lines[i + 3].strip().startswith("Section Effect:")
        ):
            formatted_lines.append("")
            formatted_lines.append(lines[i].strip())
            combined = (
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip() + " | " +
                lines[i + 3].strip()
            )
            formatted_lines.append(combined)
            i += 4
            continue

        # --- Format Section Tables entries ---
        if (
            inside_section_tables and
            i + 3 < len(lines) and
            stripped.startswith("Sub-Section Title:") and
            lines[i + 1].strip().startswith("Sub-Section Makeup:") and
            lines[i + 2].strip().startswith("Sub-Section Change:") and
            lines[i + 3].strip().startswith("Sub-Section Effect:")
        ):
            formatted_lines.append("")
            formatted_lines.append(lines[i].strip())
            combined = (
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip() + " | " +
                lines[i + 3].strip()
            )
            formatted_lines.append(combined)
            i += 4
            continue

        # --- Format outside tables: combine Section Makeup + Change + Effect only ---
        if (
            not inside_report_table and not inside_section_tables and
            i + 2 < len(lines) and
            stripped.startswith("Section Makeup:") and
            lines[i + 1].strip().startswith("Section Change:") and
            lines[i + 2].strip().startswith("Section Effect:")
        ):
            formatted_lines.append("")
            combined = (
                lines[i].strip() + " | " +
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip()
            )
            formatted_lines.append(combined)
            i += 3
            continue

        if (
            not inside_report_table and not inside_section_tables and
            i + 2 < len(lines) and
            stripped.startswith("Sub-Section Makeup:") and
            lines[i + 1].strip().startswith("Sub-Section Change:") and
            lines[i + 2].strip().startswith("Sub-Section Effect:")
        ):
            formatted_lines.append("")
            combined = (
                lines[i].strip() + " | " +
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip()
            )
            formatted_lines.append(combined)
            i += 3
            continue

        # --- Standard formatting ---
        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            full_key = f"{key.strip()}:"
            value = value.strip()
            if full_key in inline_keys:
                formatted_lines.append(lines[i])
            else:
                # Add a blank line before the key only if previous line is not already blank
                if formatted_lines and formatted_lines[-1].strip() != "":
                    formatted_lines.append("")
                formatted_lines.append(f"{full_key}")
                if value:
                    formatter = asset_formatters.get(key.strip(), lambda x: x)
                    formatted_lines.append(formatter(value))
        else:
            formatted_lines.append(lines[i])

        i += 1

    return '\n'.join(formatted_lines)

# Format full report
def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        client = data.get("client", "").strip()
        website = data.get("client_website_url", "").strip()
        context = data.get("client_context", "").strip()
        question = data.get("main_question", "").strip()
        report = data.get("report", "").strip()
        year = data.get("year", "").strip()
        combine = data.get("combine", "").strip()

        if not combine:
            raise ValueError("Missing 'combine' content in input data.")

        combine_text = convert_to_british_english(combine)
        combine_text = reformat_assets(combine_text)

        # Post-formatting: ensure a blank line above and no blank line below for specific headers
        def normalise_table_headers(text, keyword):
            lines = text.split('\n')
            new_lines = []
            i = 0
            while i < len(lines):
                if lines[i].strip() == keyword:
                    if new_lines and new_lines[-1].strip() != "":
                        new_lines.append("")  # ensure blank line before
                    new_lines.append(keyword)
                    # skip any blank line after
                    if i + 1 < len(lines) and lines[i + 1].strip() == "":
                        i += 1
                else:
                    new_lines.append(lines[i])
                i += 1
            return '\n'.join(new_lines)

        combine_text = normalise_table_headers(combine_text, "Report Table:")
        combine_text = normalise_table_headers(combine_text, "Section Tables:")

        header = f"""Client:
{to_title_case(client)}

Website:
{website}

About Client:
{to_paragraph_case(context)}

Main Question:
{to_title_case(question)}

Report:
{to_title_case(report)}

Year:
{year}

"""
        final_text = f"{header}{combine_text.strip()}"
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_text)
        logger.info(f"✅ New formatted file written to: {supabase_path}")
        try:
            content = read_supabase_file(supabase_path)
        except Exception as e:
            logger.warning(f"⚠️ Could not read file back from Supabase: {e}")
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
