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

def extract_sections(text):
    sections = {}
    section_blocks = re.findall(r"Section #: (\d+)(.*?)(?=(Section #: \d+|\Z))", text, re.DOTALL)

    for match in section_blocks:
        sec_num = match[0].strip()
        block = match[1]
        try:
            sections[sec_num] = {
                "section_no": sec_num,
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
            logger.warning(f"⚠️ Skipping section {sec_num}: {e}")
            continue
    return sections

def extract_subsections(text):
    subsections = []
    pattern = re.compile(
        r"Sub-Section #: (\d+)\.(\d+)\n.*?"
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
        re.DOTALL
    )
    matches = pattern.findall(text)
    for match in matches:
        subsections.append({
            "section_no": match[0].strip(),
            "sub_section_no": f"{match[0].strip()}.{match[1].strip()}",
            "sub_section_title": match[2].strip(),
            "sub_section_header": match[3].strip(),
            "sub_section_subheader": match[4].strip(),
            "sub_section_summary": match[5].strip(),
            "sub_section_makeup": match[6].strip(),
            "sub_section_change": match[7].strip(),
            "sub_section_effect": match[8].strip(),
            "sub_section_statistic": match[9].strip(),
            "sub_section_related_article_title": match[10].strip(),
            "sub_section_related_article_date": match[11].strip(),
            "sub_section_related_article_summary": match[12].strip(),
            "sub_section_related_article_relevance": match[13].strip(),
            "sub_section_related_article_source": match[14].strip()
        })
    return subsections

def run_prompt(payload):
    logger.info("📦 Running csv_content.py")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    logger.debug(f"🆔 Using run_id: {run_id}")

    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    logger.debug(f"🗂️ Target Supabase path: {file_path}")

    raw_text = payload.get("format_combine", "")
    raw_text = strip_excluded_blocks(raw_text)

    sections = extract_sections(raw_text)
    subsections = extract_subsections(raw_text)

    rows = []
    for sub in subsections:
        sec = sections.get(sub["section_no"], {})
        if not sec:
            logger.warning(f"⚠️ No matching section found for sub-section {sub['sub_section_no']}")
            continue
        row = {**sec, **sub}
        rows.append(row)

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
