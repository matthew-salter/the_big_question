import csv
import io
import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

SAVE_DIR = "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"

def write_section_table_formatted(path: str, section_no: str, section_title: str, rows: list[dict]):
    """
    Writes section table with layout:
    1. section_no, section_title
    2. blank line
    3. sub_section headers
    4. sub_section rows
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header block
    writer.writerow(["section_no", "section_title"])
    writer.writerow([section_no, section_title])
    writer.writerow([])

    # Write sub-section table
    writer.writerow([
        "sub_section_title",
        "sub_section_makeup",
        "sub_section_change",
        "sub_section_effect"
    ])
    for row in rows:
        writer.writerow([
            row["sub_section_title"],
            row["sub_section_makeup"],
            row["sub_section_change"],
            row["sub_section_effect"]
        ])

    # Upload to Supabase
    write_supabase_file(path, content=output.getvalue().encode("utf-8"), content_type="text/csv")


def run_prompt(payload):
    logger.info("📦 Running report_and_section_table_csv.py")
    run_id = payload.get("run_id") or str(uuid.uuid4())
    raw_text = payload.get("format_combine", "")

    results = {"run_id": run_id, "report_table": None, "section_tables": []}

    # ───── Extract Report Change Info ─────
    change_title = re.search(r"Report Change Title:\n(.+?)\n", raw_text)
    change_value = re.search(r"Report Change:\n(.+?)\n", raw_text)
    report_change_title = change_title.group(1).strip() if change_title else "Unknown"
    report_change = change_value.group(1).strip() if change_value else ""

    # ───── Extract Section Table Blocks ─────
    lines = raw_text.splitlines()
    i = 0
    current_section_no = None
    current_section_title = None

    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("Section #:"):
            current_section_no = line.split(":", 1)[1].strip()

        elif line == "Section Title:" and i + 1 < len(lines):
            current_section_title = lines[i + 1].strip()
            i += 1

        elif line == "Section Tables:":
            buffer = []
            i += 1
            while i < len(lines):
                l = lines[i].strip()
                if l.startswith(("Section #:", "Section Title:", "Sub-Section #:", "Report Change", "Report Table")):
                    break
                buffer.append(lines[i])
                i += 1

            section_rows = []
            table_text = "\n".join(buffer)
            for row in re.finditer(
                r"Sub-Section Title: (.+?)\n"
                r"Sub-Section Makeup: ([\d.]+)% \| "
                r"Sub-Section Change: ([+\-]?\d+\.\d+%) \| "
                r"Sub-Section Effect: ([+\-]?\d+\.\d+%)",
                table_text
            ):
                sub_title, makeup, change, effect = row.groups()
                section_rows.append({
                    "sub_section_title": sub_title.strip(),
                    "sub_section_makeup": makeup.strip(),
                    "sub_section_change": change.strip(),
                    "sub_section_effect": effect.strip()
                })

            if section_rows:
                filename = f"Section_Table_{current_section_no}_{current_section_title.replace(' ', '_')}_{run_id}.csv"
                path = f"{SAVE_DIR}/{filename}"
                results["section_tables"].append(path)

                write_section_table_formatted(
                    path=path,
                    section_no=current_section_no,
                    section_title=current_section_title,
                    rows=section_rows
                )

        i += 1

    return results
