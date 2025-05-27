import csv
import io
import uuid
import re
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

SAVE_DIR = "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"

# ─────────────────────────────────────────────
def write_supabase_csv(path: str, rows: list[list]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    write_supabase_file(path=path, content=output.getvalue().encode("utf-8"), content_type="text/csv")

# ─────────────────────────────────────────────
def run_report_and_section_csv(payload: dict) -> dict:
    logger.info("📦 Running report_and_section_table_csv.py")
    run_id = payload.get("run_id") or str(uuid.uuid4())
    text = payload.get("format_combine", "")
    results = {"run_id": run_id, "report_table_path": None, "section_table_paths": []}

    # ───── Report Table Extraction ─────
    report_change_title_match = re.search(r"Report Change Title:\n(.+?)\n", text)
    report_change_match = re.search(r"Report Change:\n(.+?)\n", text)
    report_table_match = re.search(r"Report Table:\n(.*?)(?=\n\S|$)", text, flags=re.DOTALL)

    if report_change_title_match and report_change_match and report_table_match:
        report_change_title = report_change_title_match.group(1).strip()
        report_change = report_change_match.group(1).strip()
        report_table_block = report_table_match.group(1).strip()

        report_rows = []
        for match in re.finditer(
            r"Section Title: (.+?)\nSection Makeup: ([\d.]+)% \| Section Change: ([+\-]?\d+\.\d+%) \| Section Effect: ([+\-]?\d+\.\d+%)",
            report_table_block
        ):
            title, makeup, change, effect = match.groups()
            report_rows.append([
                title.strip(),
                f"{makeup.strip()}%",
                change.strip(),
                effect.strip()
            ])

        if report_rows:
            report_csv = [
                [report_change_title, report_change],
                ["Report Change Title:", "Report Change:"],
                [],
                ["Section Title:", "Section Makeup:", "Section Change:", "Section Effect:"],
                *report_rows
            ]
            safe_title = re.sub(r"[^\w\s-]", "", report_change_title).strip().replace(" ", "_")
            report_filename = f"Report_Table_{safe_title}_{run_id}.csv"
            report_path = f"{SAVE_DIR}/{report_filename}"
            write_supabase_csv(report_path, report_csv)
            results["report_table_path"] = report_path

    # ───── Section Tables Extraction ─────
    section_blocks = re.finditer(
        r"Section #:\s*(\d+).*?Section Title:\n(.+?)\n.*?Section Tables:\n(.*?)(?=\n\S|$)",
        text,
        flags=re.DOTALL
    )

    for match in section_blocks:
        section_no, section_title, table_block = match.groups()
        section_no = section_no.strip()
        section_title = section_title.strip()

        section_rows = []
        for row in re.finditer(
            r"Sub-Section Title: (.+?)\n"
            r"Sub-Section Makeup: ([\d.]+)% \| "
            r"Sub-Section Change: ([+\-]?\d+\.\d+%) \| "
            r"Sub-Section Effect: ([+\-]?\d+\.\d+%)",
            table_block
        ):
            sub_title, makeup, change, effect = row.groups()
            section_rows.append([
                sub_title.strip(),
                f"{makeup.strip()}%",
                change.strip(),
                effect.strip()
            ])

        if section_rows:
            section_csv = [
                [section_no, ""],
                [section_title, "Section Title:"],
                [],
                ["Sub-Section Title", "Sub-Section Makeup", "Sub-Section Change", "Sub-Section Effect"],
                *section_rows
            ]
            safe_section_title = re.sub(r"[^\w\s-]", "", section_title).strip().replace(" ", "_")
            section_filename = f"Section_Table_{section_no}_{safe_section_title}_{run_id}.csv"
            section_path = f"{SAVE_DIR}/{section_filename}"
            write_supabase_csv(section_path, section_csv)
            results["section_table_paths"].append(section_path)

    results["section_table_paths"] = section_outputs
    results["run_id"] = run_id
    return results

# ───── Zapier-compatible alias ─────
run_prompt = run_report_and_section_csv

