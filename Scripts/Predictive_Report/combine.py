import uuid
import re
from collections import defaultdict
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def clean_text_block(text: str) -> list:
    lines = text.strip().splitlines()
    return [line.strip() for line in lines if line.strip()]

def extract_key_value_pairs(blocks: dict) -> dict:
    kv_pairs = {}
    for block in blocks.values():
        for line in block:
            if ":" in line:
                key, value = line.split(":", 1)
                kv_pairs[key.strip()] = value.strip()
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
        "Section Insight", "Section Statistic", "Section Recommendation", "Section Tables",
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

    # Intro assets
    for key in INTRO_KEYS:
        if key in kv_pairs:
            output.append(f"{key}: {kv_pairs[key]}")

    # Section and Sub-Section assets
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

    # Outro assets
    output.append("")
    for key in OUTRO_KEYS:
        if key in kv_pairs:
            output.append(f"{key}: {kv_pairs[key]}")

    return "\n".join(output)

def run_prompt(data: dict) -> dict:
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())
        data["run_id"] = run_id

        blocks = {
            "prompt_1_thinking": clean_text_block(data.get("prompt_1_thinking", "")),
            "prompt_2_section_assets": clean_text_block(data.get("prompt_2_section_assets", "")),
            "prompt_3_report_assets": clean_text_block(data.get("prompt_3_report_assets", "")),
            "prompt_4_tables": clean_text_block(data.get("prompt_4_tables", ""))
        }

        kv_pairs = extract_key_value_pairs(blocks)

        # Group section and sub-section data
        section_map = defaultdict(dict)
        subsection_map = defaultdict(lambda: defaultdict(dict))

        current_section = None
        current_sub = None

        for key, value in kv_pairs.items():
            if key == "Section #":
                match = re.match(r"(\d+)(?:\.(\d+))?", value)
                if match:
                    if match.group(2):
                        current_section = int(match.group(1))
                        current_sub = int(match.group(2))
                    else:
                        current_section = int(match.group(1))
                        current_sub = None
                continue

            if current_section is not None:
                if current_sub is not None:
                    subsection_map[current_section][current_sub][key] = value
                else:
                    section_map[current_section][key] = value

        formatted_output = build_output_from_ordered_keys(kv_pairs, section_map, subsection_map)

        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Combine/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_output)
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
