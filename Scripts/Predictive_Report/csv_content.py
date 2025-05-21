import csv, io, uuid, re
from Engine.Files.write_supabase_file import write_supabase_file
from Engine.Files.read_supabase_file import read_supabase_file
from logger import logger

# ───────────── Intro / Outro keys ──────────────
INTRO_KEYS = [
    "Client:", "Website:", "About Client:", "Main Question:", "Report:",
    "Year:", "Report Title:", "Report Sub-Title:", "Executive Summary:",
    "Key Findings:", "Call to Action:", "Report Change Title:", "Report Change:"
]
OUTRO_KEYS = ["Conclusion:", "Recommendations:"]
ALL_IO_KEYS = INTRO_KEYS + OUTRO_KEYS


# ───────────── Helpers ──────────────
def strip_excluded_blocks(text: str) -> str:
    """Remove the big ‘Report Table’ and ‘Section Tables’ blocks (leave labels)."""
    text = re.sub(r"(Report Table:\n)(.*?)(?=\nSection #:)", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(Section Tables:\n)(.*?)(?=\nSub-Section #:)", r"\1", text, flags=re.DOTALL)
    return text


def extract_intro_outro_assets(text: str) -> dict:
    """Return {csv_header: value} for every intro/outro asset, preserving order."""
    # Locate every key once
    positions = {k: text.find(k) for k in ALL_IO_KEYS}
    # Keep only keys that exist and sort by appearance in the file
    sorted_keys = sorted((k for k, pos in positions.items() if pos != -1),
                         key=lambda k: positions[k])

    asset_map = {}
    for idx, key in enumerate(sorted_keys):
        start = positions[key] + len(key)
        end = positions[sorted_keys[idx + 1]] if idx + 1 < len(sorted_keys) else len(text)
        value = text[start:end].strip().replace("\r\n", "\n").replace("\n", "\\n")
        csv_header = key[:-1].lower().replace(" ", "_")      # "Client:" → "client"
        asset_map[csv_header] = value
    # Ensure every required column exists, even if blank
    for key in ALL_IO_KEYS:
        csv_header = key[:-1].lower().replace(" ", "_")
        asset_map.setdefault(csv_header, "")
    return asset_map


# ───────────── Section / Sub-section parser (unchanged) ──────────────
def parse_sections_and_subsections(text: str):
    text = strip_excluded_blocks(text)
    rows = []
    section_blocks = re.split(r"\n(?=Section #: \d+)", text)

    for block in section_blocks:
        m_sec = re.search(r"Section #: (\d+)", block)
        if not m_sec:
            continue
        sec_no = m_sec.group(1)

        sec_data = {
            "section_no": sec_no,
            "section_title": re.search(r"Section Title:\n(.*?)\n", block),
            "section_header": re.search(r"Section Header:\n(.*?)\n", block),
            "section_subheader": re.search(r"Section Sub-Header:\n(.*?)\n", block),
            "section_theme": re.search(r"Section Theme:\n(.*?)\n", block),
            "section_summary": re.search(r"Section Summary:\n(.*?)\nSection Makeup:", block, re.DOTALL),
            "section_makeup": re.search(r"Section Makeup: (.*?) \|", block),
            "section_change": re.search(r"Section Change: ([+\-]?\d+\.\d+%)", block),
            "section_effect": re.search(r"Section Effect: ([+\-]?\d+\.\d+%)", block),
            "section_insight": re.search(r"Section Insight:\n(.*?)\n", block),
            "section_statistic": re.search(r"Section Statistic:\n(.*?)\n", block),
            "section_recommendation": re.search(r"Section Recommendation:\n(.*?)\n", block),
            "section_related_article_title": re.search(r"Section Related Article Title:\n(.*?)\n", block),
            "section_related_article_date": re.search(r"Section Related Article Date:\n(.*?)\n", block),
            "section_related_article_summary": re.search(r"Section Related Article Summary:\n(.*?)\n", block),
            "section_related_article_relevance": re.search(r"Section Related Article Relevance:\n(.*?)\n", block),
            "section_related_article_source": re.search(r"Section Related Article Source:\n(.*?)\n", block),
        }
        sec_data = {k: (v if isinstance(v, str) else v.group(1)).strip() if v else "" for k, v in sec_data.items()}

        # Sub-sections inside this section
        for sub in re.split(r"\n(?=Sub-Section #: \d+\.\d+)", block):
            m_sub = re.search(r"Sub-Section #: (\d+\.\d+)", sub)
            if not m_sub:
                continue
            sub_data = {
                "sub_section_no": m_sub.group(1),
                "sub_section_title": re.search(r"Sub-Section Title:\n(.*?)\n", sub),
                "sub_section_header": re.search(r"Sub-Section Header:\n(.*?)\n", sub),
                "sub_section_subheader": re.search(r"Sub-Section Sub-Header:\n(.*?)\n", sub),
                "sub_section_summary": re.search(r"Sub-Section Summary:\n(.*?)\nSub-Section Makeup:", sub, re.DOTALL),
                "sub_section_makeup": re.search(r"Sub-Section Makeup: (.*?) \|", sub),
                "sub_section_change": re.search(r"Sub-Section Change: ([+\-]?\d+\.\d+%)", sub),
                "sub_section_effect": re.search(r"Sub-Section Effect: ([+\-]?\d+\.\d+%)", sub),
                "sub_section_statistic": re.search(r"Sub-Section Statistic:\n(.*?)\n", sub),
                "sub_section_related_article_title": re.search(r"Sub-Section Related Article Title:\n(.*?)\n", sub),
                "sub_section_related_article_date": re.search(r"Sub-Section Related Article Date:\n(.*?)\n", sub),
                "sub_section_related_article_summary": re.search(r"Sub-Section Related Article Summary:\n(.*?)\n", sub),
                "sub_section_related_article_relevance": re.search(r"Sub-Section Related Article Relevance:\n(.*?)\n", sub),
                "sub_section_related_article_source": re.search(r"Sub-Section Related Article Source:\n(.*?)\n", sub),
            }
            sub_data = {k: (v if isinstance(v, str) else v.group(1)).strip() if v else "" for k, v in sub_data.items()}
            rows.append({**sec_data, **sub_data})
    return rows


# ───────────── Main entry ──────────────
def run_prompt(payload: dict):
    logger.info("📦 csv_content.py started")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    filepath = f"The_Big_Question/Predictive_Report/Ai_Responses/csv_Content/{run_id}.csv"
    raw_text = payload.get("format_combine", "")

    intro_outro = extract_intro_outro_assets(raw_text)
    section_rows = parse_sections_and_subsections(raw_text)
    full_rows = [{**intro_outro, **row} for row in section_rows]

    # Ordered headers (intro/outro A–O, then section columns)
    headers = list(intro_outro.keys()) + [
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
    csv.DictWriter(output, fieldnames=headers).writeheader()
    csv.DictWriter(output, fieldnames=headers).writerows(full_rows)

    write_supabase_file(path=filepath, content=output.getvalue().encode(), content_type="text/csv")
    csv_text = read_supabase_file(path=filepath, binary=False)

    return {"run_id": run_id, "csv_text": csv_text}
