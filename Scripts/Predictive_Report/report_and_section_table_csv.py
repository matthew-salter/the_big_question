import csv
import io
import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

SAVE_DIR = "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"

def run_prompt(payload):
    logger.info("📦 Running report_and_section_table_csv.py")
    run_id = payload.get("run_id") or str(uuid.uuid4())
    raw_text = payload.get("format_combine", "")

    results = {"run_id": run_id, "report_table": None, "section_tables": []}

    # ─── Extract Report Change Info ───
    change_title = re.search(r"Report Change Title:\n(.+?)\n", raw_text)
    change_value = re.search(r"Report Change:\n(.+?)\n", raw_text)
    report_change_title = change_title.group(1).strip() if change_title else "Unknown"
    report_change = change_value.group(1).strip() if change_value else ""

    # ─── Extract Report Table Block ───
    report_table_match = re.search(r"Report Table:\n(.*?)(?=\n\S|$)", raw_text, re.DOTALL)
    report_table = report_table_match.group(1).strip() if report_table_match else ""

    report_rows = []
    for match in re.finditer(
        r"Section Title: (.+?)\nSection Makeup: ([\d.]+)% \| "
        r"Section Change: ([+\-]?\d+\.\d+%) \| Section Effect: ([+\-]?\d+\.\d+%)",
        report_table
    ):
        title, makeup, change, effect = match.groups()
        report_rows.append({
            "report_change_title": report_change_title,
            "report_change": report_change,
            "section_title": title.strip(),
            "section_makeup": makeup.strip(),
            "section_change": change.strip(),
            "section_effect": effect.strip()
        })

    if report_rows:
        filename = f"Report_Table_{report_change_title.replace(' ', '_')}_{run_id}.csv"
        path = f"{SAVE_DIR}/{filename}"
        results["report_table"] = path

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=report_rows[0].keys())
        writer.writeheader()
        writer.writerows(report_rows)
        write_supabase_file(path=path, content=output.getvalue().encode("utf-8"), content_type="text/csv")

    # ─── Extract Section Table Blocks ───
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
                    "section_no": current_section_no,
                    "section_title": current_section_title,
                    "sub_section_title": sub_title.strip(),
                    "sub_section_makeup": makeup.strip(),
                    "sub_section_change": change.strip(),
                    "sub_section_effect": effect.strip()
                })

            if section_rows:
                filename = f"Section_Table_{current_section_no}_{current_section_title.replace(' ', '_')}_{run_id}.csv"
                path = f"{SAVE_DIR}/{filename}"
                results["section_tables"].append(path)

                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=section_rows[0].keys())
                writer.writeheader()
                writer.writerows(section_rows)
                write_supabase_file(path=path, content=output.getvalue().encode("utf-8"), content_type="text/csv")

        i += 1

    return results
