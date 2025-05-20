import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

def parse_section_1_and_subsections(text: str):
    rows = []

    # -----------------------------
    # Parse SECTION 1
    # -----------------------------
    section_row = {
        "section_no": "1",
        "section_title": re.search(r"Section Title:\n(.*?)\n", text).group(1).strip(),
        "section_header": re.search(r"Section Header:\n(.*?)\n", text).group(1).strip(),
        "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", text).group(1).strip(),
        "section_theme": re.search(r"Section Theme:\n(.*?)\n", text).group(1).strip(),
        "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", text, re.DOTALL).group(1).strip(),
        "section_makeup": re.search(r"Section Makeup: (.*?) \|", text).group(1).strip(),
        "section_change": re.search(r"Section Change: ([\+\-]?\d+\.\d+%)", text).group(1).strip(),
        "section_effect": re.search(r"Section Effect: ([\+\-]?\d+\.\d+%)", text).group(1).strip(),
        "section_insight": re.search(r"Section Insight:\n(.*?)\n", text).group(1).strip(),
        "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", text).group(1).strip(),
        "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", text).group(1).strip(),
        "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", text).group(1).strip(),
        "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", text).group(1).strip(),
        "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", text).group(1).strip()
    }
    rows.append(section_row)

    # -----------------------------
    # Parse SUB-SECTIONS 1.1–1.5
    # -----------------------------
    sub_sections = re.findall(
        r"Sub-Section #: 1\.(\d+).*?Sub-Section Title:\n(.*?)\n.*?"
        r"Sub-Section Header:\n(.*?)\n.*?Sub-Section Sub-Header:\n(.*?)\n.*?"
        r"Sub-Section Summary:\n(.*?)\nSub-Section Makeup: (.*?) \| "
        r"Sub-Section Change: ([\+\-]?\d+\.\d+%) \| Sub-Section Effect: ([\+\-]?\d+\.\d+%)\n.*?"
        r"Sub-Section Statistic:\n(.*?)\n.*?"
        r"Sub-Section Related Article Title:\n(.*?)\n.*?"
        r"Sub-Section Related Article Date:\n(.*?)\n.*?"
        r"Sub-Section Related Article Source:\n(.*?)\n",
        text, re.DOTALL
    )

    for s in sub_sections:
        rows.append({
            "sub_section_no": f"1.{s[0].strip()}",
            "sub_section_title": s[1].strip(),
            "sub_section_header": s[2].strip(),
            "sub_section_subheader": s[3].strip(),
            "sub_section_summary": s[4].strip(),
            "sub_section_makeup": s[5].strip(),
            "sub_section_change": s[6].strip(),
            "sub_section_effect": s[7].strip(),
            "sub_section_statistic": s[8].strip(),
            "sub_section_related_article_title": s[9].strip(),
            "sub_section_related_article_date": s[10].strip(),
            "sub_section_related_article_source": s[11].strip()
        })

    return rows


def run_prompt(payload):
    logger.info("📦 Running csv_content.py")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    logger.debug(f"🆔 Using run_id: {run_id}")

    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    logger.debug(f"🗂️ Target Supabase path: {file_path}")

    raw_text = payload.get("format_combine", "")
    rows = parse_section_1_and_subsections(raw_text)

    # --- Prepare CSV in-memory ---
    output = io.StringIO()
    writer = csv.writer(output)

    # --- Write headers (union of section and sub-section keys) ---
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())
    header_order = sorted(all_keys)  # Ensure stable order

    writer.writerow(header_order)
    for row in rows:
        writer.writerow([row.get(col, "") for col in header_order])

    csv_bytes = output.getvalue().encode("utf-8")

    # --- Upload to Supabase ---
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")

    # --- Read the uploaded CSV back as text ---
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
