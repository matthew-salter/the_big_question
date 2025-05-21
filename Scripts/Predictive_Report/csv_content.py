import csv
import io
import uuid
import re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

# ──────────── Intro / Outro Keys ────────────
INTRO_KEYS = [
    "Client:", "Website:", "About Client:", "Main Question:", "Report:", "Year:",
    "Report Title:", "Report Sub-Title:", "Executive Summary:", "Key Findings:",
    "Call to Action:", "Report Change Title:", "Report Change:"
]
OUTRO_KEYS = ["Conclusion:", "Recommendations:"]
ALL_KEYS = INTRO_KEYS + OUTRO_KEYS

# ──────────── Exclusion Strip Logic ────────────
def strip_excluded_blocks(text):
    text = re.sub(r"(Report Table:\n)(.*?)(?=\nSection #:|\Z)", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(Section Tables:\n)(.*?)(?=\nSub-Section #:|\Z)", r"\1", text, flags=re.DOTALL)
    return text

# ──────────── Intro / Outro Extraction ────────────
def extract_intro_outro_assets(text: str) -> dict:
    asset_map = {}
    lines = text.splitlines()
    current_key = None
    buffer = []

    def commit_buffer(key, buf):
        cleaned = "\n".join(buf).strip().replace("\r\n", "\n").replace("\n", "\\n")
        csv_key = key.rstrip(":").lower().replace(" ", "_")
        asset_map[csv_key] = cleaned

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ALL_KEYS:
            if current_key and buffer:
                commit_buffer(current_key, buffer)
            current_key = stripped
            buffer = []
        elif current_key:
            if stripped == "" and i + 1 < len(lines) and lines[i + 1].strip().endswith(":"):
                commit_buffer(current_key, buffer)
                current_key = None
                buffer = []
            else:
                buffer.append(line)

    if current_key and buffer:
        commit_buffer(current_key, buffer)

    for key in ALL_KEYS:
        k = key.rstrip(":").lower().replace(" ", "_")
        asset_map.setdefault(k, "")

    return asset_map

# ──────────── Section / Sub-Section Parsing ────────────
def parse_sections_and_subsections(text: str):
    rows = []
    section_blocks = re.split(r"\n(?=Section #: \d+)", text)

    for block in section_blocks:
        section_no_match = re.search(r"Section #: (\d+)", block)
        if not section_no_match:
            continue
        section_no = section_no_match.group(1)

        section_data = {
            "section_no": section_no,
            "section_title": re.search(r"Section Title:\n(.*?)\n", block),
            "section_header": re.search(r"Section Header:\n(.*?)\n", block),
            "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", block),
            "section_theme": re.search(r"Section Theme:\n(.*?)\n", block),
            "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", block, re.DOTALL),
            "section_makeup": re.search(r"Section Makeup: (.*?) \|", block),
            "section_change": re.search(r"Section Change: ([\+\-]?\d+\.\d+%)", block),
            "section_effect": re.search(r"Section Effect: ([\+\-]?\d+\.\d+%)", block),
            "section_insight": re.search(r"Section Insight:\n(.*?)\n", block),
            "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", block),
            "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", block),
            "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", block),
            "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", block),
            "section_related_article_summary": re.search(r"Section Related Article Summary:\n(.*?)\n", block),
            "section_related_article_relevance": re.search(r"Section Related Article Relevance:\n(.*?)\n", block),
            "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", block),
        }

        section_data = {
            k: (v.strip() if isinstance(v, str) else v.group(1).strip()) if v else ""
            for k, v in section_data.items()
        }

        sub_blocks = re.split(r"\n(?=Sub-Section #: \d+\.\d+)", block)
        for sub in sub_blocks:
            sub_match = re.search(r"Sub-Section #: (\d+\.\d+)", sub)
            if not sub_match:
                continue

            sub_data = {
                "sub_section_no": sub_match.group(1),
                "sub_section_title": re.search(r"Sub-Section Title:\n(.*?)\n", sub),
                "sub_section_header": re.search(r"Sub-Section Header:\n(.*?)\n", sub),
                "sub_section_subheader": re.search(r"Sub-Section Sub-Header:\n(.*?)\n", sub),
                "sub_section_summary": re.search(r"Sub-Section Summary:\n(.*?)\nSub-Section Makeup:", sub, re.DOTALL),
                "sub_section_makeup": re.search(r"Sub-Section Makeup: (.*?) \|", sub),
                "sub_section_change": re.search(r"Sub-Section Change: ([\+\-]?\d+\.\d+%)", sub),
                "sub_section_effect": re.search(r"Sub-Section Effect: ([\+\-]?\d+\.\d+%)", sub),
                "sub_section_statistic": re.search(r"Sub-Section Statistic:\n(.*?)\n", sub),
                "sub_section_related_article_title": re.search(r"Sub-Section Related Article Title:\n(.*?)\n", sub),
                "sub_section_related_article_date": re.search(r"Sub-Section Related Article Date:\n(.*?)\n", sub),
                "sub_section_related_article_summary": re.search(r"Sub-Section Related Article Summary:\n(.*?)\n", sub),
                "sub_section_related_article_relevance": re.search(r"Sub-Section Related Article Relevance:\n(.*?)\n", sub),
                "sub_section_related_article_source": re.search(r"Sub-Section Related Article Source:\n(.*?)\n", sub),
            }

            sub_data = {
                k: (v.strip() if isinstance(v, str) else v.group(1).strip()) if v else ""
                for k, v in sub_data.items()
            }

            row = {**section_data, **sub_data}
            rows.append(row)

    return rows

# ──────────── Run Prompt ────────────
def run_prompt(payload):
    logger.info("📦 Running csv_content.py (combined mode)")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    file_path = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    raw_text = strip_excluded_blocks(payload.get("format_combine", ""))

    intro_outro = extract_intro_outro_assets(raw_text)
    section_rows = parse_sections_and_subsections(raw_text)

    # Inject intro/outro data into each section row
    merged_rows = [{**intro_outro, **row} for row in section_rows]

    header_order = list(intro_outro.keys()) + [
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
    writer.writerows(merged_rows)

    csv_bytes = output.getvalue().encode("utf-8")
    write_supabase_file(path=file_path, content=csv_bytes, content_type="text/csv")
    csv_text = read_supabase_file(path=file_path, binary=False)

    return {
        "run_id": run_id,
        "csv_text": csv_text
    }
