import uuid
import re
from collections import defaultdict
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file

def clean_text_block(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.strip().split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return '\\n'.join(cleaned_lines)

def normalise_key(key: str) -> str:
    return key.replace("MakeUp", "Makeup")

def parse_hierarchical_blocks(blocks: dict) -> dict:
    structure = defaultdict(lambda: {
        "meta": {},
        "subsections": defaultdict(dict)
    })
    current_section = None
    current_sub = None

    for label, text in blocks.items():
        lines = text.split('\\n')
        for line in lines:
            if re.match(r"^Section \d+:?", line):
                current_section = int(re.findall(r"\d+", line)[0])
                current_sub = None
                continue
            elif re.match(r"^Sub-Section \d+:?", line):
                current_sub = int(re.findall(r"\d+", line)[0])
                continue
            elif ":" in line:
                key, value = line.split(":", 1)
                key = normalise_key(key.strip())
                value = value.strip()
                if current_section is not None:
                    if current_sub is not None:
                        structure[current_section]["subsections"][current_sub][key] = value
                    else:
                        structure[current_section]["meta"][key] = value
    return structure

def parse_section_tables(blocks: dict) -> dict:
    table_data = defaultdict(list)
    block = blocks.get("prompt_4_tables", "")
    lines = block.split('\\n')
    current_title = None
    for line in lines:
        if re.match(r"^[A-Z][A-Za-z \-]+:$", line):
            current_title = line.strip(':')
        elif current_title:
            table_data[current_title].append(line)
    return table_data

def extract_key_value_pairs_by_block(blocks: dict) -> dict:
    kv_pairs = {}
    for label, block in blocks.items():
        lines = block.split('\\n')
        current_key = None
        current_value = []
        inside_report_table = False
        inside_section_tables = False
        section_table_content = defaultdict(list)

        for line in lines:
            if line.startswith("Report Table:"):
                if current_key:
                    kv_pairs[current_key] = '\\n'.join(current_value).strip()
                current_key = "Report Table"
                current_value = []
                inside_report_table = True
                inside_section_tables = False
                continue

            if line.startswith("Section Tables:"):
                if current_key:
                    kv_pairs[current_key] = '\\n'.join(current_value).strip()
                current_key = None
                inside_report_table = False
                inside_section_tables = True
                current_value = []
                continue

            if inside_report_table:
                current_value.append(line)
                continue

            if inside_section_tables:
                if re.match(r"^[A-Z][A-Za-z\s\-&]+:$", line):
                    current_section = line.rstrip(":")
                else:
                    section_table_content[current_section].append(line)
                continue

            if ':' in line:
                key, value = line.split(':', 1)
                key = normalise_key(key.strip())
                value = value.strip()
                if current_key:
                    kv_pairs[current_key] = '\\n'.join(current_value).strip()
                current_key = key
                current_value = [value] if value else []
            else:
                if current_key:
                    current_value.append(line.strip())

        if current_key and not inside_report_table and not inside_section_tables:
            kv_pairs[current_key] = '\\n'.join(current_value).strip()

        if inside_report_table:
            kv_pairs["Report Table"] = '\\n'.join(current_value).strip()

        if inside_section_tables:
            formatted = []
            for sec, items in section_table_content.items():
                formatted.append(f"{sec}:")
                formatted.extend(items)
            kv_pairs["Section Tables"] = '\\n'.join(formatted)

    return kv_pairs

def build_output(kv_pairs: dict, structure: dict, section_tables: dict) -> str:
    output = []

    intro_keys = [
        "Report Title", "Report Sub-Title", "Executive Summary", "Key Findings",
        "Call to Action", "Report Change Title", "Report Change", "Report Table"
    ]
    outro_keys = ["Conclusion", "Recommendations"]

    for key in intro_keys:
        if key in kv_pairs:
            output.append(f"{key}:")
            output.append(kv_pairs[key])

    for section_num in sorted(structure.keys()):
        section = structure[section_num]
        output.append("")
        output.append(f"Section #: {section_num}")

        for key in [
            "Section Title", "Section Header", "Section Sub-Header", "Section Theme",
            "Section Summary", "Section Makeup", "Section Change", "Section Effect",
            "Section Insight", "Section Statistic", "Section Recommendation",
            "Section Related Article Title", "Section Related Article Date",
            "Section Related Article Summary", "Section Related Article Relevance",
            "Section Related Article Source"]:
            if key in section["meta"]:
                output.append(f"{key}: {section['meta'][key]}")

        section_title = section["meta"].get("Section Title")
        if section_title and section_title in section_tables:
            output.append("Section Tables:")
            output.extend(section_tables[section_title])

        for sub_num in sorted(section["subsections"].keys()):
            output.append("")
            output.append(f"Sub-Section #: {section_num}.{sub_num}")
            sub = section["subsections"][sub_num]
            for key in [
                "Sub-Section Title", "Sub-Section Header", "Sub-Section Sub-Header",
                "Sub-Section Summary", "Sub-Section Makeup", "Sub-Section Change", "Sub-Section Effect",
                "Sub-Section Statistic", "Sub-Section Related Article Title",
                "Sub-Section Related Article Date", "Sub-Section Related Article Summary",
                "Sub-Section Related Article Relevance", "Sub-Section Related Article Source"]:
                if key in sub:
                    output.append(f"{key}: {sub[key]}")

    output.append("")
    for key in outro_keys:
        if key in kv_pairs:
            output.append(f"{key}:")
            output.append(kv_pairs[key])

    return '\n'.join(output)

def run_prompt(data: dict) -> dict:
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())
        data["run_id"] = run_id

        flat_blocks = {
            "prompt_1_thinking": clean_text_block(data.get("prompt_1_thinking", "")),
            "prompt_2_section_assets": clean_text_block(data.get("prompt_2_section_assets", "")),
            "prompt_3_report_assets": clean_text_block(data.get("prompt_3_report_assets", "")),
            "prompt_4_tables": clean_text_block(data.get("prompt_4_tables", ""))
        }

        kv_pairs = extract_key_value_pairs_by_block(flat_blocks)
        structure = parse_hierarchical_blocks(flat_blocks)
        section_tables = parse_section_tables(flat_blocks)

        formatted_output = build_output(kv_pairs, structure, section_tables)
        final_output = formatted_output.replace('\\n', '\n')

        supabase_path = f"Predictive_Report/Ai_Responses/Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_output)
        logger.info(f"✅ Structured section output written to: {supabase_path}")

        try:
            content = read_supabase_file(supabase_path)
            logger.info(f"📥 Retrieved structured output from Supabase for run_id: {run_id}")
        except Exception as read_error:
            logger.warning(f"⚠️ Could not read file back from Supabase immediately: {read_error}")
            content = final_output

        return {
            "status": "success",
            "run_id": run_id,
            "path": supabase_path,
            "structured_output": content.strip()
        }

    except Exception as e:
        logger.exception("❌ combine.py failed")
        return {
            "status": "error",
            "message": str(e)
        }
