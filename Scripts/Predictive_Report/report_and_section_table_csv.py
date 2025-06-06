import csv
import io
import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

SAVE_DIR = "Predictive_Report/Ai_Responses/Report_and_Section_Tables"

# ─────────────────────────────────────────────
# Write section tables (already working)
# ─────────────────────────────────────────────
def write_section_table_formatted(path: str, section_no: str, section_title: str, rows: list[dict]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section_no", section_no])
    writer.writerow(["section_title", section_title])
    writer.writerow([])
    writer.writerow(["sub_section_title", "sub_section_makeup", "sub_section_change", "sub_section_effect"])
    for row in rows:
        writer.writerow([
            row["sub_section_title"],
            f'{row["sub_section_makeup"]}%' if not row["sub_section_makeup"].endswith('%') else row["sub_section_makeup"],
            f'{row["sub_section_change"]}%' if not row["sub_section_change"].endswith('%') else row["sub_section_change"],
            f'{row["sub_section_effect"]}%' if not row["sub_section_effect"].endswith('%') else row["sub_section_effect"],
        ])
    write_supabase_file(path=path, content=output.getvalue().encode("utf-8"), content_type="text/csv")

# ─────────────────────────────────────────────
# Write report table (new functionality)
# ─────────────────────────────────────────────
def write_report_table_formatted(path: str, report_change_title: str, report_change: str, rows: list[dict]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["report_change_title", report_change_title])  # A1
    writer.writerow(["report_change", report_change])              # B1
    writer.writerow([])                                            # Blank row
    writer.writerow(["section_title", "section_makeup", "section_change", "section_effect"])  # Header row
    for row in rows:
        writer.writerow([
            row["section_title"],
            f'{row["section_makeup"]}%' if not row["section_makeup"].endswith('%') else row["section_makeup"],
            f'{row["section_change"]}%' if not row["section_change"].endswith('%') else row["section_change"],
            f'{row["section_effect"]}%' if not row["section_effect"].endswith('%') else row["section_effect"]
        ])
    write_supabase_file(path=path, content=output.getvalue().encode("utf-8"), content_type="text/csv")

# ─────────────────────────────────────────────
# Main Entry
# ─────────────────────────────────────────────
def run_prompt(payload):
    logger.info("\U0001F4E6 Running report_and_section_table_csv.py")
    run_id = payload.get("run_id") or str(uuid.uuid4())
    raw_text = payload.get("format_combine", "")

    results = {"run_id": run_id, "report_table": None, "section_tables": []}

    # ───── Extract Report Change Info ─────
    change_title_match = re.search(r"Report Change Title:\n(.+?)\n", raw_text)
    change_value_match = re.search(r"Report Change:\n(.+?)\n", raw_text)
    report_change_title = change_title_match.group(1).strip() if change_title_match else "Unknown"
    report_change = change_value_match.group(1).strip() if change_value_match else ""

    # ───── Extract Report Table Block ─────
    report_table_match = re.search(r"Report Table:\n(.*?)(?=\n(?:Section #:|\Z))", raw_text, flags=re.DOTALL)
    if report_table_match:
        table_text = report_table_match.group(1)
        report_rows = []
        for row in re.finditer(
            r"Section Title: (.+?)\n"
            r"Section Makeup: ([\d.]+)%? \| Section Change: ([+\-]?[\d.]+%) \| Section Effect: ([+\-]?[\d.]+%)",
            table_text
        ):
            section_title, makeup, change, effect = row.groups()
            report_rows.append({
                "section_title": section_title.strip(),
                "section_makeup": makeup.strip(),
                "section_change": change.strip(),
                "section_effect": effect.strip()
            })

        if report_rows:
            filename = f"Report_Table_{report_change_title.replace(' ', '_')}_{run_id}.csv"
            path = f"{SAVE_DIR}/{filename}"
            results["report_table"] = path

            write_report_table_formatted(
                path=path,
                report_change_title=report_change_title,
                report_change=report_change,
                rows=report_rows
            )

    # ───── Parse Section Tables (unchanged) ─────
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
                r"Sub-Section Makeup: ([\d.]+)%? \| Sub-Section Change: ([+\-]?[\d.]+%) \| Sub-Section Effect: ([+\-]?[\d.]+%)",
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

# ───── Zapier-compatible alias ─────
run_report_and_section_csv = run_prompt
run_prompt = run_report_and_section_csv
