# Scripts/Explainer_Report/question_assets.py

import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse

import requests
from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# =========================
# Config
# =========================

QUESTIONS_PATH = "Prompts/Explainer_Report/Questions/questions.txt"
PROMPT_PATH = "Prompts/Explainer_Report/prompt_1_question_assets.txt"
SUPABASE_BASE_DIR = "Explainer_Report/Ai_Responses/Question_Assets"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Sliding window used for prompt context only
MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "12"))
MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "16000"))

# Disallowed URL signatures (to block downloads)
BAD_URL_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
BAD_URL_SNIPPETS = ("/pdf/", "/download", "?download=")

HTTP_UA = os.getenv(
    "HTTP_VALIDATION_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = float(os.getenv("HTTP_VALIDATION_TIMEOUT", "8.0"))

SUMMARY_MIN = 750
SUMMARY_MAX = 900

# =========================
# Helpers
# =========================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.strip().lower())
    return s.strip("-")

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]

def safe_escape_braces(value: str) -> str:
    return str(value).replace("{", "{{").replace("}", "}}")

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_questions(path: str) -> List[str]:
    return [ln.strip() for ln in load_text(path).splitlines() if ln.strip()]

def format_question(q_template: str, ctx: Dict[str, Any]) -> str:
    safe_ctx = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
    return q_template.format(**safe_ctx)

def build_prior_context(history: List[str]) -> str:
    if not history:
        return ""
    joined = "\n\n".join(history[-MAX_QA_IN_CONTEXT:])
    joined = joined[-MAX_CONTEXT_CHARS:]
    return (
        "\n\n---\n### PRIOR RESPONSES CONTEXT\n"
        "The following are previous question/answer JSONs from this same report run:\n"
        f"{joined}\n---\n"
    )

# --- Sanitizers & validators ---

URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
MD_LINK_RE = re.compile(r'\[[^\]]+\]\(\s*https?://[^)]+\)', re.IGNORECASE)

def strip_links(text: str) -> str:
    if not isinstance(text, str):
        return text
    def _strip_md(m):
        inner = m.group(0)
        inner = re.sub(r'\(\s*https?://[^)]+\)', '', inner)
        return inner.replace("[]", "").strip()
    text = MD_LINK_RE.sub(_strip_md, text)
    text = URL_RE.sub('', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def hostname(url: str) -> str:
    try:
        return urlparse(url).netloc.split(":")[0].lower()
    except Exception:
        return ""

def is_bad_article_url(url: str) -> bool:
    if not url or not url.startswith("https://"):
        return True
    lo = url.lower()
    if any(lo.endswith(ext) for ext in BAD_URL_HINTS):
        return True
    if any(sn in lo for sn in BAD_URL_SNIPPETS):
        return True
    return False

def is_http_html_ok(url: str) -> Tuple[bool, str]:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": HTTP_UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return False, f"status={r.status_code}"
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype:
            return False, f"content_type={ctype or 'unknown'}"
        head = (r.content[:4096] or b"").lower()
        if b"<html" not in head:
            return False, "no_html_marker"
        return True, "ok"
    except Exception as exc:
        return False, f"exception={type(exc).__name__}"

def normalise_bullets(s: str) -> str:
    if not isinstance(s, str):
        return s
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', s) if p.strip()]
    while len(parts) < 4 and any((';' in x or ':' in x) for x in parts):
        idx = next((i for i,x in enumerate(parts) if (';' in x or ':' in x)), None)
        if idx is None: break
        frag = parts.pop(idx)
        if ';' in frag:
            a, b = frag.split(';', 1)
        else:
            a, b = frag.split(':', 1)
        parts[idx:idx] = [a.strip() + '.', b.strip() + '.']
    while len(parts) < 4:
        parts.append('')
    parts = parts[:4]
    parts = [p if p.endswith(('.', '!', '?')) else (p + '.') for p in parts]
    return "\n".join(parts)

def fingerprint(text: str) -> str:
    t = (text or '').lower()
    t = re.sub(r'\d+(\.\d+)?%?', 'X', t)
    t = re.sub(r'\s+', '', t)
    return t[:160]

ALLOWED_TOP_KEYS = {
    "Question", "Header", "Sub-Header", "Summary",
    "Bullet Points", "Statistic", "Insight", "Related Article"
}
ALLOWED_RA_KEYS = {
    "Related Article Title", "Related Article Date", "Related Article Summary",
    "Related Article Relevance", "Related Article Source", "Related Article URL"
}

def filter_extra_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Remove any unexpected top-level keys (e.g., _meta)
    clean = {k: v for k, v in obj.items() if k in ALLOWED_TOP_KEYS}
    ra = clean.get("Related Article")
    if isinstance(ra, dict):
        clean["Related Article"] = {k: v for k, v in ra.items() if k in ALLOWED_RA_KEYS}
    return clean

def validate_summary_format(summary: str) -> None:
    if not isinstance(summary, str):
        raise ValueError("Summary missing or not a string.")
    total_len = len(summary)
    if total_len < SUMMARY_MIN or total_len > SUMMARY_MAX:
        raise ValueError(f"Summary length {total_len} outside {SUMMARY_MIN}-{SUMMARY_MAX} chars.")
    parts = summary.split("\n\n")
    if not (3 <= len(parts) <= 5):
        raise ValueError("Summary must have 3–5 paragraphs separated by \\n\\n.")
    # Light guard against bullet-like elements
    if any(p.strip().startswith(("-", "*", "•", "1.", "2.", "3.")) for p in parts):
        raise ValueError("Summary must be narrative paragraphs, not list-style.")

# =========================
# OpenAI call
# =========================

def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = TEMPERATURE) -> Dict[str, Any]:
    client = OpenAI()
    max_tries, base_sleep = 6, 1.0
    for attempt in range(1, max_tries + 1):
        try:
            resp = client.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                input=prompt
            )
            text_out = getattr(resp, "output_text", None)
            if not text_out and hasattr(resp, "output") and resp.output:
                text_out = resp.output[0].content[0].text
            if not text_out:
                raise ValueError("Empty response from model")
            return json.loads(text_out)
        except Exception as e:
            if attempt == max_tries:
                raise
            delay = base_sleep * (2 ** (attempt - 1)) + 0.25 * (attempt - 1)
            logger.warning(f"⚠️ OpenAI error (attempt {attempt}/{max_tries}): {e}. Backing off {delay:.2f}s")
            time.sleep(delay)

# =========================
# Supabase helpers
# =========================

def supabase_write_txt(path: str, content: str):
    write_supabase_file(path, content, content_type="text/plain; charset=utf-8")

def supabase_write_textjson(path: str, obj: Dict[str, Any]):
    supabase_write_txt(path, json.dumps(obj, ensure_ascii=False, indent=2))

def supabase_paths(run_id: str) -> Dict[str, str]:
    base = f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs"
    return {
        "base": base,
        "manifest": f"{base}/manifest.json",
        "checkpoint": f"{base}/checkpoint.json",
    }

# =========================
# Validation pipeline
# =========================

def sanitise_and_validate(
    obj: Dict[str, Any],
    run_seen_urls: set,
    run_seen_statfp: set,
    run_seen_insfp: set
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Returns (clean_obj, warnings).
    Hard fail: bad/missing article URL (download), live check not HTML/200, summary format/length violation, missing required keys.
    Soft warn: duplicate URL vs run, near-dup Statistic/Insight vs run.
    """
    warnings: List[str] = []

    # Remove extra keys early
    obj = filter_extra_keys(obj)

    # Required keys quick check
    required = {"Question","Header","Sub-Header","Summary","Bullet Points","Statistic","Insight","Related Article"}
    if any(k not in obj for k in required):
        missing = [k for k in required if k not in obj]
        raise ValueError(f"Missing keys: {missing}")

    # Strip any links from non-article fields
    for fld in ("Summary", "Bullet Points", "Statistic", "Insight", "Header", "Sub-Header", "Question"):
        if fld in obj:
            obj[fld] = strip_links(obj[fld])

    # Summary strict validation
    validate_summary_format(obj["Summary"])

    # Bullet normalization to exactly 4 sentences / 3 newlines
    if "Bullet Points" in obj:
        obj["Bullet Points"] = normalise_bullets(obj["Bullet Points"])
        if obj["Bullet Points"].count("\n") != 3:
            raise ValueError("Bullet Points must contain exactly four sentences separated by three \\n characters.")

    # Uniqueness (soft) across entire run
    stp = fingerprint(obj.get("Statistic", ""))
    inp = fingerprint(obj.get("Insight", ""))
    if stp and stp in run_seen_statfp:
        warnings.append("statistic_near_duplicate")
    if inp and inp in run_seen_insfp:
        warnings.append("insight_near_duplicate")

    # Validate article URL (hard for broken, soft for duplicate)
    ra = obj.get("Related Article") or {}
    if not isinstance(ra, dict):
        raise ValueError("Related Article must be an object.")
    ra = {k: v for k, v in ra.items() if k in ALLOWED_RA_KEYS}
    url = (ra.get("Related Article URL") or "").strip()
    if is_bad_article_url(url):
        raise ValueError(f"Related Article URL is a download or invalid: {url}")
    ok, info = is_http_html_ok(url)
    if not ok:
        raise ValueError(f"Related Article URL failed live check ({info}): {url}")
    if url in run_seen_urls:
        warnings.append("related_article_url_duplicate")

    obj["Related Article"] = ra
    return obj, warnings

def fallback_not_applicable(question_text: str) -> Dict[str, Any]:
    return {
        "Question": question_text,
        "Header": "Not Applicable",
        "Sub-Header": "Not Applicable",
        "Summary": "Not Applicable",
        "Bullet Points": "Not Applicable\nNot Applicable\nNot Applicable\nNot Applicable",
        "Statistic": "Not Applicable",
        "Insight": "Not Applicable",
        "Related Article": {
            "Related Article Title": "Not Applicable",
            "Related Article Date": "Not Applicable",
            "Related Article Summary": "Not Applicable",
            "Related Article Relevance": "Not Applicable",
            "Related Article Source": "Not Applicable",
            "Related Article URL": "Not Applicable"
        }
    }

# =========================
# Core worker
# =========================

def _process_run(run_id: str, payload: Dict[str, Any]) -> None:
    try:
        logger.info(f"🚀 [Explainer.Run] start run_id={run_id}")
        ctx = {
            "condition": payload.get("condition", ""),
            "age": payload.get("age", ""),
            "gender": payload.get("gender", ""),
            "ethnicity": payload.get("ethnicity", ""),
            "region": payload.get("region", ""),
            "todays_date": payload.get("todays_date", ""),
        }

        prompt_template = load_text(PROMPT_PATH)
        q_templates = load_questions(QUESTIONS_PATH)
        total = len(q_templates)
        paths = supabase_paths(run_id)

        manifest = {
            "run_id": run_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "total": total,
            "items": [],
            "payload_meta": {"model": DEFAULT_MODEL, "temperature": TEMPERATURE, "ctx": ctx},
        }
        ckpt = {"last_completed_index": -1, "updated_at": now_iso()}
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        history_for_prompt: List[str] = []

        # Run-wide seen sets
        run_seen_urls: set = set()
        run_seen_statfp: set = set()
        run_seen_insfp: set = set()

        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            filled_q = format_question(q_tmpl, ctx)
            mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
            mapping["question"] = safe_escape_braces(filled_q)

            prior_block = build_prior_context(history_for_prompt)
            prompt = prompt_template.format(**mapping) + prior_block

            q_id = f"{idx+1:02d}_{slugify(filled_q)[:50]}_{sha8(filled_q)}"
            outfile = f'{paths["base"]}/{q_id}.txt'
            item_meta = {
                "q_id": q_id,
                "index": idx,
                "question_filled": filled_q,
                "status": "started",
                "started_at": now_iso(),
                "output_path": outfile
            }
            manifest["items"].append(item_meta)
            supabase_write_textjson(paths["manifest"], manifest)

            gen_attempts = 2
            last_warnings: List[str] = []
            hard_error: Optional[str] = None

            for attempt in range(1, gen_attempts + 1):
                try:
                    t0 = time.time()
                    obj = call_openai(prompt, model=DEFAULT_MODEL, temperature=TEMPERATURE)
                    obj, last_warnings = sanitise_and_validate(obj, run_seen_urls, run_seen_statfp, run_seen_insfp)
                    elapsed = round(time.time() - t0, 3)

                    # Persist output WITHOUT extra keys
                    supabase_write_txt(outfile, json.dumps(obj, ensure_ascii=False, indent=2))

                    status_value = "done_with_warnings" if last_warnings else "done"
                    # Update seen sets after successful write
                    ra = obj["Related Article"]
                    url = (ra.get("Related Article URL") or "").strip()
                    st = obj.get("Statistic") or ""
                    ins = obj.get("Insight") or ""
                    stat_fp = fingerprint(st) if st else ""
                    ins_fp  = fingerprint(ins) if ins else ""
                    if url: run_seen_urls.add(url)
                    if stat_fp: run_seen_statfp.add(stat_fp)
                    if ins_fp: run_seen_insfp.add(ins_fp)

                    item_meta.update({
                        "status": status_value,
                        "completed_at": now_iso(),
                        "latency_seconds": elapsed,
                        "warnings": last_warnings,
                        "related_article_url": url,
                        "stat_fp": stat_fp,
                        "ins_fp": ins_fp
                    })
                    supabase_write_textjson(paths["manifest"], manifest)

                    ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                    supabase_write_textjson(paths["checkpoint"], ckpt)

                    history_for_prompt.append(json.dumps(obj, ensure_ascii=False))
                    time.sleep(0.25)
                    hard_error = None
                    break

                except Exception as e:
                    hard_error = str(e)
                    logger.warning(f"🔁 Attempt {attempt}/{gen_attempts} failed for q_id={q_id}: {hard_error}")

            if hard_error:
                fb = fallback_not_applicable(filled_q)
                supabase_write_txt(outfile, json.dumps(fb, ensure_ascii=False, indent=2))

                item_meta.update({
                    "status": "done_with_fallback",
                    "completed_at": now_iso(),
                    "warnings": ["fallback_not_applicable"],
                    "error": hard_error
                })
                supabase_write_textjson(paths["manifest"], manifest)

                ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                supabase_write_textjson(paths["checkpoint"], ckpt)

                history_for_prompt.append(json.dumps(fb, ensure_ascii=False))

        logger.info(f"✅ [Explainer.Run] completed run_id={run_id} total={total}")

    except Exception as outer:
        logger.exception(f"❌ [Explainer.Run] fatal for run_id={run_id}: {outer}")

# =========================
# Entrypoint
# =========================

def run_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    run_id = data.get("run_id") or f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    data["run_id"] = run_id

    logger.info("📥 question_assets.run_prompt payload:")
    logger.info(json.dumps({
        "run_id": run_id,
        "condition": data.get("condition"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "ethnicity": data.get("ethnicity"),
        "region": data.get("region"),
        "todays_date": data.get("todays_date"),
        "model": DEFAULT_MODEL,
    }, ensure_ascii=False))

    t = threading.Thread(target=_process_run, args=(run_id, data), daemon=True)
    t.start()

    return {
        "status": "processing",
        "run_id": run_id,
        "message": "Explainer report run started. Results will stream into Supabase.",
        "supabase_base_dir": f"{SUPABASE_BASE_DIR}/{run_id}/Individual_Question_Outputs/"
    }
