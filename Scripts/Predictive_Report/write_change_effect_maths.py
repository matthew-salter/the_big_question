import uuid
import yaml
import json
from threading import Thread
from logger import logger
from decimal import Decimal, ROUND_HALF_UP
from Engine.Files.write_supabase_file import write_supabase_file

# --- Formatters ---
def format_integer_percent(value: float) -> str:
    return f"{int(round(value))}%"

def format_decimal_percent(value: float) -> str:
    return f"{Decimal(value).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"

# --- Core transformation ---
def build_structured_output(prompt_1_thinking: dict) -> dict:
    result = {}

    for section_key in sorted(prompt_1_thinking.keys()):
        if not section_key.lower().startswith("section "):
            continue
        section_data = prompt_1_thinking[section_key]
        sub_sections = {}
        sub_section_effects = []

        # Extract top-level section metadata
        section_title = section_data.get("Section Title", "").strip()
        section_summary = section_data.get("Section Summary", "").strip()
        section_makeup_str = section_data.get("Section MakeUp", "0%").strip().replace('%', '')

        try:
            section_makeup = float(section_makeup_str)
        except ValueError:
            section_makeup = 0.0

        # --- Build ordered section dict ---
        section_output = {}
        section_output["Section Title"] = section_title
        section_output["Section Summary"] = section_summary
        section_output["Section MakeUp"] = format_integer_percent(section_makeup)

        # Placeholder – these get filled after sub-sections processed
        section_output["Section Change"] = None
        section_output["Section Effect"] = None

        if "Section Related Article" in section_data:
            section_output["Section Related Article"] = section_data["Section Related Article"]

        # --- Sub-section processing ---
        for sub_key in sorted(section_data.keys()):
            sub_data = section_data[sub_key]
            if (
                isinstance(sub_data, dict)
                and sub_key.lower().startswith("sub-section ")
                and "Sub-Section Title" in sub_data
            ):
                sub_output = {}
                sub_output["Sub-Section Title"] = sub_data.get("Sub-Section Title", "").strip()
                sub_output["Sub-Section Summary"] = sub_data.get("Sub-Section Summary", "").strip()

                sub_makeup_str = sub_data.get("Sub-Section MakeUp", "0%").strip().replace('%', '')
                sub_change_str = sub_data.get("Sub-Section Change", "0%").strip().replace('%', '')

                try:
                    sub_makeup = float(sub_makeup_str)
                    sub_change = float(sub_change_str)
                    sub_effect = (sub_makeup / 100) * sub_change
                except ValueError:
                    sub_makeup = 0.0
                    sub_change = 0.0
                    sub_effect = 0.0

                sub_output["Sub-Section MakeUp"] = format_integer_percent(sub_makeup)
                sub_output["Sub-Section Change"] = format_decimal_percent(sub_change)
                sub_output["Sub-Section Effect"] = format_decimal_percent(sub_effect)

                if "Sub-Section Related Article" in sub_data:
                    sub_output["Sub-Section Related Article"] = sub_data["Sub-Section Related Article"]

                sub_sections[sub_key] = sub_output
                sub_section_effects.append(sub_effect)

        # --- Now calculate section-level metrics
        section_change = sum(sub_section_effects)
        section_effect = (section_makeup / 100) * section_change
        section_output["Section Change"] = format_decimal_percent(section_change)
        section_output["Section Effect"] = format_decimal_percent(section_effect)

        # Append sub-sections after all section-level fields
        for sub_key, sub_data in sub_sections.items():
            section_output[sub_key] = sub_data

        result[section_key] = section_output

    return result

# --- Write logic ---
def background_task(run_id: str, raw_data: dict):
    filename = f"{run_id}.txt"
    supabase_path = f"Predictive_Report/Ai_Responses/Change_Effect_Maths/{filename}"

    try:
        raw_prompt = raw_data.get("prompt_1_thinking", "")
        prompt_data = yaml.safe_load(raw_prompt)
        structured_output = build_structured_output(prompt_data)
        text_output = json.dumps(structured_output, indent=2)
    except Exception as e:
        text_output = f"Failed to process data: {str(e)}"

    write_supabase_file(supabase_path, text_output)

def run_prompt(data):
    run_id = str(uuid.uuid4())
    Thread(target=background_task, args=(run_id, data)).start()
    return {"run_id": run_id}
