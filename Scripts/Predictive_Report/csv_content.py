import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

def strip_excluded_blocks(text):
    # Keep labels, only remove content in between Report Table and Section #, and Section Tables and Sub-Section #
    text = re.sub(r"(Report Table:\n)(.*?)(?=\nSection #:)", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(Section Tables:\n)(.*?)(?=\nSub-Section #:)", r"\1", text, flags=re.DOTALL)
    return text

def parse_all_sections_and_subsections(text: str):
    text = strip_excluded_blocks(text)
    rows = []

    # Split by sections
    section_blocks = re.split(r"(Section #: \d+)", text)
    section_pairs = [(section_blocks[i], section_blocks[i+1]) for i in range(1, len(section_blocks), 2)]

    for label, content in section_pairs:
        section_no_match = re.search(r"\d+", label)
        section_no = section_no_match.group(0) if section_no_match else ""

        section_raw = {
            "section_title": re.search(r"Section Title:\n(.*?)\n", content),
            "section_header": re.search(r"Section Header:\n(.*?)\n", content),
            "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", content),
            "section_theme": re.search(r"Section Theme:\n(.*?)\n", content),
            "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", content, re.DOTALL),
            "section_makeup": re.search(r"Section Makeup: (.*?) \|", content),
            "section_change": re.search(r"Section Change: ([\+\-]?\d+\.\d+%)", content),
            "section_effect": re.search(r"Section Effect: ([\+\-]?\d+\.\d+%)", content),
            "section_insight": re.search(r"Section Insight:\n(.*?)\n", content),
            "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", content),
            "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", content),
            "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", content),
            "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", content),
            "section_related_article_summary": re.search(r"Section Related Article Summary:\n(.*?)\n", content),
            "section_related_article_relevance": re.search(r"Section Related Article Relevance:\n(.*?)\n", content),
            "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", content)
        }
        section_data = {"section_no": section_no}
        section_data.update({k: (v.group(1).strip() if v else "") for k, v in section_raw.items()})

        # Match all sub-sections inside this section
        sub_matches = re.findall(
            r"Sub-Section #: (\d+\.\d+).*?"
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
            content,
            flags=re.DOTALL
        )

        for match in sub_matches:
            sub_data = {
                "sub_section_no": match[0],
                "sub_section_title": match[1],
                "sub_section_header": match[2],
                "sub_section_subheader": match[3],
                "sub_section_summary": match[4],
                "sub_section_makeup": match[5],
                "sub_section_change": match[6],
                "sub_section_effect": match[7],
                "sub_section_statistic": match[8],
                "sub_section_related_article_title": match[9],
                "sub_section_related_article_date": match[10],
                "sub_section_related_article_summary": match[11],
                "sub_section_related_article_relevance": match[12],
                "sub_section_related_article_source": match[13]
            }
            combined = {**section_data, **sub_data}
            rows.append(combined)

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
    writer = csv.DictWriter(output, fieldnames=header_order)
    writer.writeheader()
    writer.writerows(rows)

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
