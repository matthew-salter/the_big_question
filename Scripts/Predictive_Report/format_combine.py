import re
import uuid
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file
from Prompts.American_to_British.convert_spellings import convert_to_british_english
from Prompts.Text_Styling.formatting import (
    to_title_case,
    to_sentence_case,
    to_paragraph_case,
    format_bullet_points,
)

# Formatting map
format_map = {
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

def clean_text(text):
    text = re.sub(r'[\t\r]+', '', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()

def apply_formatting(text):
    lines = text.splitlines()
    formatted_lines = []

    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            formatter = format_map.get(key, lambda x: x)
            formatted_lines.append(f"{key}:{formatter(value)}")
        else:
            formatted_lines.append(line.strip())

    return '\n'.join(formatted_lines)

def format_report_table_block(text):
    pattern = r"(Report Table:\n)(.*?)(?=\n[A-Z][a-zA-Z ]*?:)"
    def repl(match):
        block = match.group(2).strip().splitlines()
        output = [match.group(1).strip()]
        i = 0
        while i < len(block):
            if block[i].startswith("Section Title:"):
                title = block[i].strip()
                makeup = block[i+1].strip()
                change = block[i+2].strip()
                effect = block[i+3].strip()
                makeup_val = makeup.split(":", 1)[1].strip()
                change_val = change.split(":", 1)[1].strip()
                effect_val = effect.split(":", 1)[1].strip()
                summary_line = f"Section Makeup: {makeup_val} | Section Change: {change_val} | Section Effect: {effect_val}"
                output.append(title)
                output.append(summary_line)
                output.append("")  # blank line
                i += 4
            else:
                output.append(block[i])
                i += 1
        return '\n'.join(output).strip()
    return re.sub(pattern, repl, text, flags=re.DOTALL)

def format_section_tables_blocks(text):
    pattern = r"(Section Tables:\n)(.*?)(?=\nSection Related Article Title:)"
    def repl(match):
        block = match.group(2).strip().splitlines()
        output = [match.group(1).strip()]
        i = 0
        while i < len(block):
            if block[i].startswith("Sub-Section Title:"):
                title = block[i].strip()
                makeup = block[i+1].strip()
                change = block[i+2].strip()
                effect = block[i+3].strip()
                makeup_val = makeup.split(":", 1)[1].strip()
                change_val = change.split(":", 1)[1].strip()
                effect_val = effect.split(":", 1)[1].strip()
                summary_line = f"Sub-Section Makeup: {makeup_val} | Sub-Section Change: {change_val} | Sub-Section Effect: {effect_val}"
                output.append(title)
                output.append(summary_line)
                output.append("")  # blank line
                i += 4
            else:
                output.append(block[i])
                i += 1
        return '\n'.join(output).strip()
    return re.sub(pattern, repl, text, flags=re.DOTALL)

def run_prompt(data):
    try:
        run_id = str(uuid.uuid4())
        raw_text = data.get("prompt_5_combine", "")
        cleaned = clean_text(raw_text)
        converted = convert_to_british_english(cleaned)
        formatted = apply_formatting(converted)
        formatted = format_report_table_block(formatted)
        formatted = format_section_tables_blocks(formatted)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Format_Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted)
        logger.info(f"✅ Output written to Supabase: {supabase_path}")
        return {"status": "success", "run_id": run_id, "formatted_content": formatted}

    except Exception as e:
        logger.exception("❌ Error in format_combine.py")
        return {"status": "error", "message": str(e)}
