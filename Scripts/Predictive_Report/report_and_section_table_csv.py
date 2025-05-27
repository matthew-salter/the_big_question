import csv
import io
import uuid
import re
from pathlib import Path

# ──────────────────────────────
# CONFIGURATION
# ──────────────────────────────
SAVE_DIR = "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"

def write_local_file(path: str, content: bytes):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)

# ──────────────────────────────
# MAIN PARSING FUNCTION
# ──────────────────────────────
def run_report_and_section_csv(payload: dict) -> dict:
    run_id = payload.get("run_id") or str(uuid.uuid4())
    text = payload.get("format_combine", "")

    results = {}

    # ───── Extract Report Change Details ─────
    report_change_title = re.search(r"Report Change Title:\n(.+?)\n", text)
    report_change_value = re.search(r"Report Change:\n(.+?)\n", text)
    report_change_title = report_change_title.group(1).strip() if report_change_title else ""
    report_change_value = report_change_value.group(1).strip() if report_change_value else ""

    # ───── Extract Report Table ─────
    report_table_match = re.search(r"Report Table:\n(.*?)(?=\n\S|$)", text, flags=re.DOTALL)
    report_table_block = report_table_match.group(1).strip() if report_table_match else ""

    report_rows = []
    for match in re.finditer(
        r"Section Title: (.+?)\nSection Makeup: ([\d.]+)% \| Section Change: ([+\-]?\d+\.\d+%) \| Section Effect: ([+\-]?\d+\.\d+%)",
        report_table_block
    ):
        title, makeup, change, effect = match.groups()
        report_rows.append({
            "report_change_title": report_change_title,
            "report_change": report_change_value,
            "section_title": title.strip(),
            "section_makeup": makeup.strip(),
            "section_change": change.strip(),
            "section_effect": effect.strip()
        })

    if report_rows:
        report_filename = f"Report_Table_{report_change_title.replace(' ', '_')}_{run_id}.csv"
        report_path = f"{SAVE_DIR}/{report_filename}"
        results['report_table_path'] = report_path

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=report_rows[0].keys())
        writer.writeheader()
        writer.writerows(report_rows)
        write_local_file(report_path, output.getvalue().encode("utf-8"))

    # ───── Extract Section Table Blocks ─────
    section_blocks = re.finditer(
        r"Section #:\s*(\d+).*?Section Title:\n(.+?)\n.*?Section Tables:\n(.*?)(?=\n\S|$)",
        text,
        flags=re.DOTALL
    )

    section_outputs = []
    for match in section_blocks:
        section_no, section_title, table_block = match.groups()
        section_no = section_no.strip()
        section_title_clean = section_title.strip()
        table_block = table_block.strip()

        section_rows = []
        for row in re.finditer(
            r"Sub-Section Title: (.+?)\nSub-Section Makeup: ([\d.]+)% \| Sub-Section Change: ([+\-]?\d+\.\d+%) \| Sub-Section Effect: ([+\-]?\d+\.\d+%)",
            table_block
        ):
            sub_title, makeup, change, effect = row.groups()
            section_rows.append({
                "section_no": section_no,
                "section_title": section_title_clean,
                "sub_section_title": sub_title.strip(),
                "sub_section_makeup": makeup.strip(),
                "sub_section_change": change.strip(),
                "sub_section_effect": effect.strip()
            })

        if section_rows:
            section_filename = f"Section_Table_{section_no}_{section_title_clean.replace(' ', '_')}_{run_id}.csv"
            section_path = f"{SAVE_DIR}/{section_filename}"
            section_outputs.append(section_path)

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=section_rows[0].keys())
            writer.writeheader()
            writer.writerows(section_rows)
            write_local_file(section_path, output.getvalue().encode("utf-8"))

    results['section_table_paths'] = section_outputs
    results['run_id'] = run_id
    return results
