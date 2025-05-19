import uuid
import re
from collections import defaultdict
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def clean_text_block(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.strip().split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return '\\n'.join(cleaned_lines)

def extract_key_value_pairs_by_block(blocks: dict) -> dict:
    kv_pairs = {}
    for label, block in blocks.items():
        lines = block.split('\\n')
        current_key = None
        current_value = []
        inside_report_table = False
        inside_section_tables = False
        section_table_content = defaultdict(list)
        capture_next = None

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
                if re.match(r'^[A-Z][A-Za-z\s\-]+:', line):
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
                key = key.strip()
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

def build_output_from_ordered_keys(kv_pairs: dict, section_map: dict, subsection_map: dict) -> str:
    output = []

    INTRO_KEYS = [
        "Report Title", "Report Sub-Title", "Executive Summary", "Key Findings",
        "Call to Action", "Report Change Title", "Report Change", "Report Table"
    ]

    SECTION_KEYS = [
        "Section Title", "Section Header", "Section Sub-Header", "Section Theme",
        "Section Summary", "Section Makeup", "Section Change", "Section Effect",
        "Section Insight", "Section Statistic", "Section Recommendation",
        "Section Related Article Title", "Section Related Article Date",
        "Section Related Article Summary", "Section Related Article Relevance",
        "Section Related Article Source"
    ]

    SUBSECTION_KEYS = [
        "Sub-Section Title", "Sub-Section Header", "Sub-Section Sub-Header",
        "Sub-Section Summary", "Sub-Section Makeup", "Sub-Section Change", "Sub-Section Effect",
        "Sub-Section Statistic", "Sub-Section Related Article Title",
        "Sub-Section Related Article Date", "Sub-Section Related Article Summary",
        "Sub-Section Related Article Relevance", "Sub-Section Related Article Source"
    ]

    OUTRO_KEYS = ["Conclusion", "Recommendations"]

    for key in INTRO_KEYS:
        if key in kv_pairs:
            output.append(f"{key}:")
            output.append(kv_pairs[key])

    for section_num in sorted(section_map.keys()):
        output.append("")
        output.append(f"Section #: {section_num}")
        section_data = section_map[section_num]
        for key in SECTION_KEYS:
            if key in section_data:
                output.append(f"{key}: {section_data[key]}")

        for sub_num in sorted(subsection_map[section_num].keys()):
            output.append("")
            output.append(f"Section #: {section_num}.{sub_num}")
            sub_data = subsection_map[section_num][sub_num]
            for key in SUBSECTION_KEYS:
                if key in sub_data:
                    output.append(f"{key}: {sub_data[key]}")

    if "Section Tables" in kv_pairs:
        output.append("")
        output.append("Section Tables:")
        output.append(kv_pairs["Section Tables"])

    output.append("")
    for key in OUTRO_KEYS:
        if key in kv_pairs:
            output.append(f"{key}:")
            output.append(kv_pairs[key])

    return "\n".join(output)

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

        section_map = defaultdict(dict)
        subsection_map = defaultdict(lambda: defaultdict(dict))

        current_section = None
        current_subsection = None
        section_counter = 1
        subsection_counter = defaultdict(int)

        for key, value in kv_pairs.items():
            if re.match(r"Section \d+", key):
                current_section = int(re.findall(r"\d+", key)[0])
                continue
            elif re.match(r"Sub-Section \d+", key):
                if current_section is None:
                    current_section = section_counter
                    section_counter += 1
                subsection_counter[current_section] += 1
                current_subsection = subsection_counter[current_section]
                continue

            if current_section is not None and current_subsection is not None and key.startswith("Sub-Section"):
                subsection_map[current_section][current_subsection][key] = value
            elif current_section is not None:
                section_map[current_section][key] = value

        formatted_output = build_output_from_ordered_keys(kv_pairs, section_map, subsection_map)
        final_output = formatted_output.replace('\\n', '\n')

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Combine/{run_id}.txt"
        write_supabase_file(supabase_path, final_output)
        logger.info(f"✅ Reordered structured output written to: {supabase_path}")

        return {
            "status": "success",
            "run_id": run_id,
            "path": supabase_path
        }

    except Exception as e:
        logger.exception("❌ combine.py failed")
        return {
            "status": "error",
            "message": str(e)
        }
