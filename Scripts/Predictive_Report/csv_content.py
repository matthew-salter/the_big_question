import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

def run_prompt(payload):
    logger.info("📦 Running csv_content.py")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    logger.debug(f"🆔 Using run_id: {run_id}")

    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    logger.debug(f"🗂️ Target Supabase path: {file_path}")

    raw_text = payload.get("format_combine", "")

    # Remove Report Table and Section Table blocks
    raw_text = re.sub(r"Report Table:(.*?)Section #:", "", raw_text, flags=re.DOTALL)
    raw_text = re.sub(r"Section Tables:(.*?)Sub-Section #:", "", raw_text, flags=re.DOTALL)

    # Split by Section
    section_blocks = re.split(r"(?=Section #: \d+)\n", raw_text)

    parsed_rows = []

    for section_block in section_blocks:
        section_no_match = re.search(r"Section #: (\d+)", section_block)
        if not section_no_match:
            continue

        section_no = section_no_match.group(1)

        try:
            section = {
                "section_no": section_no,
                "section_title": re.search(r"Section Title:\n(.*?)\n", section_block).group(1).strip(),
                "section_header": re.search(r"Section Header:\n(.*?)\n", section_block).group(1).strip(),
                "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", section_block).group(1).strip(),
                "section_theme": re.search(r"Section Theme:\n(.*?)\n", section_block).group(1).strip(),
                "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", section_block, re.DOTALL).group(1).strip(),
                "section_makeup": re.search(r"Section Makeup: (.*?) \|", section_block).group(1).strip(),
                "section_change": re.search(r"Section Change: ([\+\-]?\d+\.\d+%)", section_block).group(1).strip(),
                "section_effect": re.search(r"Section Effect: ([\+\-]?\d+\.\d+%)", section_block).group(1).strip(),
                "section_insight": re.search(r"Section Insight:\n(.*?)\n", section_block).group(1).strip(),
                "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", section_block).group(1).strip(),
                "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", section_block).group(1).strip(),
                "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", section_block).group(1).strip(),
                "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", section_block).group(1).strip(),
                "section_related_article_summary": re.search(r"Section Related Article Summary:\n(.*?)\n", section_block).group(1).strip(),
                "section_related_article_relevance": re.search(r"Section Related Article Relevance:\n(.*?)\n", section_block).group(1).strip(),
                "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", section_block).group(1).strip()
            }
        except Exception as e:
            logger.warning(f"⚠️ Skipping section {section_no}: {e}")
            continue

        # Find all sub-sections inside the section
        sub_blocks = re.split(r"(?=Sub-Section #: \d+\.\d+)\n", section_block)

        for sub_block in sub_blocks:
            match = re.search(
                r"Sub-Section #: (\d+)\.(\d+).*?"
                r"Sub-Section Title:\n(.*?)\n.*?"
                r"Sub-Section Header:\n(.*?)\n.*?"
                r"Sub-Section Sub-Header:\n(.*?)\n.*?"
                r"Sub-Section Summary:\n(.*?)\nSub-Section Makeup: (.*?) \| "
                r"Sub-Section Change: ([\+\-]?\d+\.\d+%) \| Sub-Section Effect: ([\+\-]?\d+\.\d+%)\n.*?"
                r"Sub-Section Statistic:\n(.*?)\n.*?"
                r"Sub-Section Related Article Title:\n(.*?)\n.*?"
                r"Sub-Section Related Article Date:\n(.*?)\n.*?"
                r"Sub-Section Related Article Summary:\n(.*?)\n.*?"
                r"Sub-Section Related Article Relevance:\n(.*?)\n.*?"
                r"Sub-Section Related Article Source:\n(.*?)\n",
                sub_block, re.DOTALL
            )
            if match:
                parsed_rows.append({
                    **section,
                    "sub_section_no": f"{match.group(1)}.{match.group(2)}",
                    "sub_section_title": match.group(3).strip(),
                    "sub_section_header": match.group(4).strip(),
                    "sub_section_subheader": match.group(5).strip(),
                    "sub_section_summary": match.group(6).strip(),
                    "sub_section_makeup": match.group(7).strip(),
                    "sub_section_change": match.group(8).strip(),
                    "sub_section_effect": match.group(9).strip(),
                    "sub_section_statistic": match.group(10).strip(),
                    "sub_section_related_article_title": match.group(11).strip(),
                    "sub_section_related_article_date": match.group(12).strip(),
                    "sub_section_related_article_summary": match.group(13).strip(),
                    "sub_section_related_article_relevance": match.group(14).strip(),
                    "sub_section_related_article_source": match.group(15).strip()
                })

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

    for row in parsed_rows:
        writer.writerow([row.get(col, "") for col in header_order])

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
