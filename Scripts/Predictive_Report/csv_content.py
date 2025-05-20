import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

def strip_excluded_blocks(text):
    text = re.sub(r"Report Table:(.*?)Section #:", "", text, flags=re.DOTALL)
    text = re.sub(r"Section Tables:(.*?)Sub-Section #:", "", text, flags=re.DOTALL)
    return text

def parse_all_sections_and_subsections(text: str):
    text = strip_excluded_blocks(text)
    rows = []

    # Find all Section blocks
    section_pattern = r"Section #: (\d+)(.*?)(?=Section #: \d+|\Z)"
    section_matches = list(re.finditer(section_pattern, text, re.DOTALL))

    for section_match in section_matches:
        section_no = section_match.group(1).strip()
        block = section_match.group(2)

        try:
            section_row = {
                "section_no": section_no,
                "section_title": re.search(r"Section Title:\n(.*?)\n", block).group(1).strip(),
                "section_header": re.search(r"Section Header:\n(.*?)\n", block).group(1).strip(),
                "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", block).group(1).strip(),
                "section_theme": re.search(r"Section Theme:\n(.*?)\n", block).group(1).strip(),
                "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", block, re.DOTALL).group(1).strip(),
                "section_makeup": re.search(r"Section Makeup: (.*?) \|", block).group(1).strip(),
                "section_change": re.search(r"Section Change: ([\+\-]?\d+\.\d+%)", block).group(1).strip(),
                "section_effect": re.search(r"Section Effect: ([\+\-]?\d+\.\d+%)", block).group(1).strip(),
                "section_insight": re.search(r"Section Insight:\n(.*?)\n", block).group(1).strip(),
                "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", block).group(1).strip(),
                "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", block).group(1).strip(),
                "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", block).group(1).strip(),
                "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", block).group(1).strip(),
                "section_related_article_summary": re.search(r"Section Related Article Summary:\n(.*?)\n", block).group(1).strip(),
                "section_related_article_relevance": re.search(r"Section Related Article Relevance:\n(.*?)\n", block).group(1).strip(),
                "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", block).group(1).strip()
            }
        except Exception as e:
            logger.warning(f"⚠️ Skipping section {section_no} due to missing field: {e}")
            continue

        # Find sub-sections for this section
        subsection_pattern = rf"Sub-Section #: {section_no}\.\d+.*?Sub-Section Title:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Header:\n(.*?)\n.*?Sub-Section Sub-Header:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Summary:\n(.*?)\nSub-Section Makeup: (.*?) \| "
        subsection_pattern += rf"Sub-Section Change: ([\+\-]?\d+\.\d+%) \| Sub-Section Effect: ([\+\-]?\d+\.\d+%)\n.*?"
        subsection_pattern += rf"Sub-Section Statistic:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Related Article Title:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Related Article Date:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Related Article Summary:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Related Article Relevance:\n(.*?)\n.*?"
        subsection_pattern += rf"Sub-Section Related Article Source:\n(.*?)\n"

        subsection_matches = re.findall(subsection_pattern, block, re.DOTALL)

        for idx, s in enumerate(subsection_matches, start=1):
            row = section_row.copy()
            row.update({
                "sub_section_no": f"{section_no}.{idx}",
                "sub_section_title": s[0].strip(),
                "sub_section_header": s[1].strip(),
                "sub_section_subheader": s[2].strip(),
                "sub_section_summary": s[3].strip(),
                "sub_section_makeup": s[4].strip(),
                "sub_section_change": s[5].strip(),
                "sub_section_effect": s[6].strip(),
                "sub_section_statistic": s[7].strip(),
                "sub_section_related_article_title": s[8].strip(),
                "sub_section_related_article_date": s[9].strip(),
                "sub_section_related_article_summary": s[10].strip(),
                "sub_section_related_article_relevance": s[11].strip(),
                "sub_section_related_article_source": s[12].strip()
            })
            rows.append(row)

    return rows

def run_prompt(payload):
    logger.info("📦 Running csv_content.py")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    logger.debug(f"🆔 Using run_id: {run_id}")

    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    logger.debug(f"🗂️ Target Supabase path: {file_path}")

    raw_text = payload.get("format_combine", "")
    rows = parse_all_sections_and_subsections(raw_text)

    header_order = [
        "section_no", "section_title", "section_header", "section_subheader", "section_theme",
        "section_summary", "section_makeup", "section_change", "section_effect",
        "section_insight", "section_statistic", "section_recommendation",
        "section_related_article_title", "section_related_article_date",
        "section_related_article_summary", "section_related_article_relevance",
        "section_related_article_source",
        "sub_section_no", "sub_section_title", "sub_section_header", "sub_section_subheader",
        "sub_section_summary", "sub_section_makeup", "sub_section_change", "sub_section_effect",
        "sub_section_statistic", "sub_section_related_article_title", "sub_section_related_article_date",
        "sub_section_related_article_summary", "sub_section_related_article_relevance",
        "sub_section_related_article_source"
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header_order)

    for row in rows:
        writer.writerow([row.get(col, "") for col in header_order])

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
