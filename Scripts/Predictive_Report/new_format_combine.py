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
    "About Client": to_paragraph_case,
    "Main Question": to_title_case,
    "Report": to_title_case,
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
    "Sub-Section Title": to_title_case,
    "Sub-Section Header": to_title_case,
    "Sub-Section Sub-Header": to_title_case,
    "Sub-Section Summary": to_paragraph_case,
    "Sub-Section Statistic": to_sentence_case,
    "Sub-Section Related Article Title": to_title_case,
    "Sub-Section Related Article Date": to_title_case,
    "Sub-Section Related Article Summary": to_paragraph_case,
    "Sub-Section Related Article Relevance": to_paragraph_case,
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

# Indent block content
def indent_block_content(text, start_marker, end_marker):
    pattern = re.compile(rf'({re.escape(start_marker)}\n)(.*?)(?=\n{re.escape(end_marker)})', re.DOTALL)
    def replacer(match):
        header = match.group(1)
        block_content = match.group(2)
        indented = '\n'.join(['\t' + line if line.strip() else '' for line in block_content.split('\n')])
        return header + indented
    return re.sub(pattern, replacer, text)

# Reformat assets
def reformat_assets(text):
    inline_keys = {
        "Section #:", "Section Makeup:", "Section Change:", "Section Effect:",
        "Sub-Section #:", "Sub-Section Makeup:", "Sub-Section Change:", "Sub-Section Effect:"
    }
    lines = text.split('\n')
    formatted_lines = []
    inside_table_block = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped in {"Report Table:", "Section Tables:"}:
            inside_table_block = True
        elif stripped.startswith("Section #:") or stripped.startswith("Sub-Section #:"):
            inside_table_block = False

        if inside_table_block or not stripped:
            formatted_lines.append(lines[i])
            i += 1
            continue

        if stripped.startswith("Section Makeup:") and i + 2 < len(lines):
            formatted_lines.append("")
            combined = lines[i].strip() + " | " + lines[i + 1].strip() + " | " + lines[i + 2].strip()
            formatted_lines.append(combined)
            i += 3
            continue

        if stripped.startswith("Sub-Section Makeup:") and i + 2 < len(lines):
            formatted_lines.append("")
            combined = lines[i].strip() + " | " + lines[i + 1].strip() + " | " + lines[i + 2].strip()
            formatted_lines.append(combined)
            i += 3
            continue

        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            full_key = f"{key.strip()}:"
            value = value.strip()
            if full_key in inline_keys:
                formatted_lines.append(lines[i])
            else:
                formatted_lines.append(f"\n{full_key}")
                if value:
                    formatter = asset_formatters.get(key.strip(), lambda x: x)
                    formatted_lines.append(formatter(value))
        else:
            formatted_lines.append(lines[i])
        i += 1
    return '\n'.join(formatted_lines)

# Format Report & Section Tables
def collapse_table_blocks(text):
    lines = text.split("\n")
    output = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Match Section Table block
        if (
            line.startswith("Section Title:") and
            i + 3 < len(lines) and
            lines[i + 1].strip().startswith("Section Makeup:") and
            lines[i + 2].strip().startswith("Section Change:") and
            lines[i + 3].strip().startswith("Section Effect:")
        ):
            output.append("")  # blank line before block
            output.append(lines[i].strip())
            combined = (
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip() + " | " +
                lines[i + 3].strip()
            )
            output.append(combined)
            i += 4
            continue

        # Match Sub-Section Table block
        if (
            line.startswith("Sub-Section Title:") and
            i + 3 < len(lines) and
            lines[i + 1].strip().startswith("Sub-Section Makeup:") and
            lines[i + 2].strip().startswith("Sub-Section Change:") and
            lines[i + 3].strip().startswith("Sub-Section Effect:")
        ):
            output.append("")  # blank line before block
            output.append(lines[i].strip())
            combined = (
                lines[i + 1].strip() + " | " +
                lines[i + 2].strip() + " | " +
                lines[i + 3].strip()
            )
            output.append(combined)
            i += 4
            continue

        output.append(lines[i])
        i += 1

    return "\n".join(output)

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
        combine_text = indent_block_content(combine_text, "Report Table:", "Section #:")
        combine_text = indent_block_content(combine_text, "Section Tables:", "Sub-Section #:")
        combine_text = reformat_assets(combine_text)

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
        collapsed_text = collapse_table_blocks(combine_text)
        final_text = f"{header}{collapsed_text.strip()}"
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/New_Format_Combine/{run_id}.txt"
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
