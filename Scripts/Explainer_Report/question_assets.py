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

# Sliding window used for prompt tone/context only (NOT for uniqueness)
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
ACRO_RE = re.compile(r"\b[A-Z]{2,}\b")

def strip_links(text: str) -> str:
    """Remove any URLs/markdown links but preserve all original whitespace/newlines."""
    if not isinstance(text, str):
        return text

    # Remove markdown links but keep anchor text
    def _strip_md(m):
        inner = m.group(0)
        inner = re.sub(r'\(\s*https?://[^)]+\)', '', inner)
        # drop surrounding [ and ] only
        return re.sub(r'^\[|\]$', '', inner)

    text = MD_LINK_RE.sub(_strip_md, text)
    # Remove raw URLs, leave whitespace untouched
    return URL_RE.sub('', text)

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

def is_http_html_ok(url: str) -> Tuple[bool, str, str]:
    """
    (ok, info, final_url) for public HTML article pages.

    Key behaviours:
    - Canonicalise to final URL.
    - Only treat 'deny' as blocking if NO article signals are present.
    - Article signals (any one passes):
        * <article> tag, OR
        * <h1> + >=2 <p> + body len >= 1500, OR
        * >=3 'citation_*' meta tags, OR
        * JSON-LD type "ScholarlyArticle".
    - Reject AMP/proxy and non-HTML.
    """
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": HTTP_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            },
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        final_url = r.url

        if r.status_code != 200:
            return False, f"status={r.status_code}", final_url

        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype:
            return False, f"content_type={ctype or 'unknown'}", final_url

        body = r.text or ""
        bl = body.lower()

        if "<html" not in bl:
            return False, "no_html_marker", final_url

        # ---- Article signals (broadened) ----
        has_article_tag = "<article" in bl
        has_h1 = "<h1" in bl
        p_count = bl.count("<p")
        long_enough = len(body) >= 1500
        citation_meta_count = body.count('name="citation_') + body.count("name='citation_")
        has_scholarly_jsonld = '"ScholarlyArticle"' in bl

        article_signals = (
            has_article_tag
            or (has_h1 and p_count >= 2 and long_enough)
            or (citation_meta_count >= 3)
            or has_scholarly_jsonld
        )

        # ---- Deny/interstitial markers (block ONLY if no article signals) ----
        deny_markers = (
            "access denied", "permission denied", "request blocked",
            "enable cookies", "unusual traffic", "captcha",
            "attention required!", "blocked your request", "reference #",
            "to protect our site"
        )
        has_deny = any(m in bl for m in deny_markers)
        if has_deny and not article_signals:
            return False, "access_denied_interstitial", final_url

        if not article_signals:
            return False, "insufficient_article_signals", final_url

        # ---- Reject AMP/proxy variants ----
        ful = final_url.lower()
        if "/amp" in ful or ful.startswith("https://amp.") or "amp." in hostname(final_url):
            return False, "amp_or_proxy_url", final_url

        return True, "ok", final_url

    except Exception as exc:
        return False, f"exception={type(exc).__name__}", url

def fingerprint(text: str) -> str:
    t = (text or '').lower()
    t = re.sub(r'\d+(\.\d+)?%?', 'X', t)
    t = re.sub(r'\s+', '', t)
    return t[:160]

def is_recent_ddmmyyyy(ddmmyyyy: str, months_primary=6, months_max=12) -> Tuple[bool, bool]:
    """Return (within_primary, within_max) for DD/MM/YYYY."""
    try:
        d = datetime.strptime(ddmmyyyy, "%d/%m/%Y").date()
    except Exception:
        return False, False
    today = datetime.utcnow().date()
    delta_days = (today - d).days
    return (delta_days <= months_primary * 30), (delta_days <= months_max * 30)

# =========================
# OpenAI call (Responses API + web_search)
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
    run_seen_insfp: set,
    policy: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Returns (clean_obj, warnings). Hard failures raise to trigger retry.
    Hard fail conditions depend on policy:
      - bad/missing article URL (download or invalid)
      - live check not HTML/200, interstitial/AMP/proxy, or not article-like
      - recency beyond policy['max_months'] (if provided)
      - duplicate URL if policy['require_unique'] is True
      - duplicate Statistic/Insight fingerprints (always hard fail)
    """
    warnings: List[str] = []

    # Strip any links from non-article fields (preserve whitespace/newlines)
    for fld in ("Summary", "Bullet Points", "Statistic", "Insight", "Header", "Sub-Header", "Question"):
        if fld in obj:
            obj[fld] = strip_links(obj[fld])

    # Uniqueness (fingerprints) across entire run: enforce as hard fail
    st_text = obj.get("Statistic", "") or ""
    in_text = obj.get("Insight", "") or ""
    stp = fingerprint(st_text)
    inp = fingerprint(in_text)
    if stp and stp in run_seen_statfp:
        raise ValueError("statistic_near_duplicate")
    if inp and inp in run_seen_insfp:
        raise ValueError("insight_near_duplicate")

    # Validate article URL (shape + live HTML + not an interstitial/AMP + canonical final URL)
    ra = obj.get("Related Article") or {}
    url = (ra.get("Related Article URL") or "").strip()

    if is_bad_article_url(url):
        raise ValueError(f"Related Article URL is a download or invalid: {url}")

    ok, info, final_url = is_http_html_ok(url)
    if not ok:
        raise ValueError(f"Related Article URL failed live check ({info}): {url}")

    # Canonicalise to final URL
    url = final_url
    ra["Related Article URL"] = url

    # Recency policy
    max_months = policy.get("max_months", 6)
    if max_months is not None:
        within_6, within_12 = is_recent_ddmmyyyy(ra.get("Related Article Date", ""))
        if max_months <= 6 and not within_6:
            raise ValueError("related_article_older_than_6m")
        if max_months > 6 and not within_12:
            raise ValueError("related_article_older_than_12m")
        if within_12 and not within_6 and max_months > 6:
            warnings.append("related_article_between_6_and_12_months")
    # Attempt 3 uses max_months=None -> skip recency entirely

    # URL uniqueness policy
    require_unique = bool(policy.get("require_unique", True))
    if require_unique and url in run_seen_urls:
        raise ValueError("related_article_url_duplicate")
    if (not require_unique) and url in run_seen_urls:
        warnings.append("related_article_url_duplicate_allowed")

    obj["Related Article"] = ra
    return obj, warnings

def fallback_not_applicable(question_text: str) -> Dict[str, Any]:
    """Produce a safe fallback JSON so no question is ever missing."""
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

        # Seed REGISTRY memory from payload (cross-run)
        registry = payload.get("REGISTRY", {}) or {}
        run_seen_urls: set = set(registry.get("URLS_USED", []) or [])
        run_seen_statfp: set = set(registry.get("STATS_FINGERPRINTS_USED", []) or [])
        run_seen_insfp: set = set(registry.get("INSIGHTS_FINGERPRINTS_USED", []) or [])
        run_seen_stats_exact: set = set(registry.get("STATS_USED", []) or [])
        run_seen_ins_exact: set = set(registry.get("INSIGHTS_USED", []) or [])
        run_seen_acros: set = set(registry.get("ACRONYMS_SEEN", []) or [])

        manifest = {
            "run_id": run_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "total": total,
            "items": [],
            "payload_meta": {
                "model": DEFAULT_MODEL,
                "temperature": TEMPERATURE,
                "ctx": ctx,
                "seed_registry_counts": {
                    "URLS_USED": len(run_seen_urls),
                    "STATS_FINGERPRINTS_USED": len(run_seen_statfp),
                    "INSIGHTS_FINGERPRINTS_USED": len(run_seen_insfp),
                    "STATS_USED": len(run_seen_stats_exact),
                    "INSIGHTS_USED": len(run_seen_ins_exact),
                    "ACRONYMS_SEEN": len(run_seen_acros),
                }
            },
        }
        ckpt = {"last_completed_index": -1, "updated_at": now_iso()}
        supabase_write_textjson(paths["manifest"], manifest)
        supabase_write_textjson(paths["checkpoint"], ckpt)

        history_for_prompt: List[str] = []

        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            filled_q = format_question(q_tmpl, ctx)
            mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
            mapping["question"] = safe_escape_braces(filled_q)

            # --- Inject REGISTRY placeholders into mapping before formatting the prompt ---
            def _lines(xs):
                """Return sorted newline-joined string or empty string."""
                return "\n".join(sorted(xs)) if xs else ""

            mapping.update({
                "urls_used_each_on_new_line": _lines(run_seen_urls),
                "stats_used_each_on_new_line": _lines(run_seen_stats_exact),
                "insights_used_each_on_new_line": _lines(run_seen_ins_exact),
                "stats_fps_each_on_new_line": _lines(run_seen_statfp),
                "insights_fps_each_on_new_line": _lines(run_seen_insfp),
                "acronyms_each_on_new_line": _lines(run_seen_acros),
            })

            # Build prompt (REGISTRY placeholders now populated)
            prior_block = build_prior_context(history_for_prompt)
            base_prompt = prompt_template.format(**mapping) + prior_block

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

            # Three attempts:
            # 1) strict: ≤6m, unique URL, live HTML required
            # 2) lenient: ≤12m, duplicates allowed, live HTML required
            # 3) salvage: no date limit, duplicates allowed; if live HTML fails, write with URL="Unavailable"
            gen_attempts = 3
            last_warnings: List[str] = []
            hard_error: Optional[str] = None
            last_fail_reason: Optional[str] = None

            for attempt in range(1, gen_attempts + 1):
                try:
                    policy = {
                        # max_months=None => skip recency check
                        "max_months": 6 if attempt == 1 else (12 if attempt == 2 else None),
                        "require_unique": True if attempt == 1 else False,  # attempt 2 & 3 allow duplicates
                    }

                    retry_hint = ""
                    if attempt > 1 and last_fail_reason:
                        retry_hint = (
                            "\n\n---\n## RETRY CONTEXT\n"
                            f"Previous attempt failed: {last_fail_reason}\n"
                            "Choose a Related Article URL that:\n"
                            "• loads as public HTML (HTTP 200), not AMP/proxy/download/interstitial;\n"
                            f"• {'is ≤ 6 months old' if attempt == 1 else ('is ≤ 12 months old' if attempt == 2 else 'may be any date (no limit)')};\n"
                            f"• {'is NOT in URLS_USED' if attempt == 1 else 'may reuse a URL if necessary'}.\n"
                            "Avoid reusing Statistic/Insight fingerprints when possible.\n---\n"
                        )

                    prompt = base_prompt + retry_hint

                    t0 = time.time()
                    obj = call_openai(prompt, model=DEFAULT_MODEL, temperature=TEMPERATURE)
                    obj, last_warnings = sanitise_and_validate(
                        obj,
                        run_seen_urls,
                        run_seen_statfp,
                        run_seen_insfp,
                        policy
                    )
                    elapsed = round(time.time() - t0, 3)

                    # Persist output
                    supabase_write_txt(outfile, json.dumps(obj, ensure_ascii=False, indent=2))
                    status_value = "done_with_warnings" if last_warnings else "done"
                    item_meta.update({"status": status_value, "completed_at": now_iso(), "latency_seconds": elapsed, "warnings": last_warnings})
                    supabase_write_textjson(paths["manifest"], manifest)

                    # Advance checkpoint
                    ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                    supabase_write_textjson(paths["checkpoint"], ckpt)

                    # Update run-wide seen sets AFTER successful validation
                    ra = obj.get("Related Article") or {}
                    url = (ra.get("Related Article URL") or "").strip()
                    if url and url != "Unavailable":
                        run_seen_urls.add(url)

                    st = obj.get("Statistic") or ""
                    ins = obj.get("Insight") or ""
                    if st:
                        run_seen_statfp.add(fingerprint(st))
                        run_seen_stats_exact.add(st.strip())
                    if ins:
                        run_seen_insfp.add(fingerprint(ins))
                        run_seen_ins_exact.add(ins.strip())

                    # naive acronym scrape
                    fields_to_scan = [
                        obj.get("Header",""), obj.get("Sub-Header",""),
                        obj.get("Summary",""), obj.get("Bullet Points",""),
                        obj.get("Statistic",""), obj.get("Insight","")
                    ]
                    found_acros = set()
                    for f in fields_to_scan:
                        found_acros.update(ACRO_RE.findall(f or ""))
                    for a in found_acros:
                        run_seen_acros.add(a)

                    history_for_prompt.append(json.dumps(obj, ensure_ascii=False))
                    time.sleep(0.25)
                    hard_error = None
                    last_fail_reason = None
                    break

                except Exception as e:
                    hard_error = str(e)
                    last_fail_reason = hard_error
                    logger.warning(f"🔁 Attempt {attempt}/{gen_attempts} failed for q_id={q_id}: {hard_error}")

                    # ---- Attempt 3 salvage: if live HTML/URL shape failed, accept output but blank the URL ----
                    is_last_attempt = (attempt == gen_attempts)
                    url_failure_signals = (
                        "Related Article URL failed live check" in hard_error
                        or "Related Article URL is a download or invalid" in hard_error
                        or "amp_or_proxy_url" in hard_error
                        or "no_html_marker" in hard_error
                        or "insufficient_article_signals" in hard_error
                        or "content_type=" in hard_error
                        or "status=" in hard_error
                    )

                    if is_last_attempt and url_failure_signals:
                        # Try to get the model's raw JSON if obj isn't available yet
                        try:
                            if 'obj' not in locals() or obj is None:
                                obj = call_openai(prompt, model=DEFAULT_MODEL, temperature=TEMPERATURE)
                        except Exception:
                            obj = fallback_not_applicable(filled_q)

                        # Strip links from non-article fields (preserve newlines)
                        for fld in ("Summary", "Bullet Points", "Statistic", "Insight", "Header", "Sub-Header", "Question"):
                            if fld in obj:
                                obj[fld] = strip_links(obj[fld])

                        # Force URL to "Unavailable", keep every other field as generated
                        ra = obj.get("Related Article") or {}
                        ra["Related Article URL"] = "Unavailable"
                        obj["Related Article"] = ra

                        # Persist salvaged output
                        supabase_write_txt(outfile, json.dumps(obj, ensure_ascii=False, indent=2))
                        item_meta.update({
                            "status": "done_with_warnings",
                            "completed_at": now_iso(),
                            "warnings": ["related_article_unavailable_salvaged"],
                            "error": hard_error
                        })
                        supabase_write_textjson(paths["manifest"], manifest)

                        ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                        supabase_write_textjson(paths["checkpoint"], ckpt)

                        # Update seen sets from non-URL assets only
                        st = obj.get("Statistic") or ""
                        ins = obj.get("Insight") or ""
                        if st:
                            run_seen_statfp.add(fingerprint(st))
                            run_seen_stats_exact.add(st.strip())
                        if ins:
                            run_seen_insfp.add(fingerprint(ins))
                            run_seen_ins_exact.add(ins.strip())

                        history_for_prompt.append(json.dumps(obj, ensure_ascii=False))
                        time.sleep(0.25)
                        hard_error = None  # treat as success-with-warnings
                        break

            # If still failing after retries (and not salvageable), write a "Not Applicable" fallback
            if hard_error:
                fb = fallback_not_applicable(filled_q)
                supabase_write_txt(outfile, json.dumps(fb, ensure_ascii=False, indent=2))

                item_meta.update({"status": "done_with_fallback", "completed_at": now_iso(), "warnings": ["fallback_not_applicable"], "error": hard_error})
                supabase_write_textjson(paths["manifest"], manifest)

                ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                supabase_write_textjson(paths["checkpoint"], ckpt)

                # keep history minimal for fallback (do not add to run_seen to avoid poisoning uniqueness)
                history_for_prompt.append(json.dumps(fb, ensure_ascii=False))

        # Optionally persist final REGISTRY snapshot for cross-run seeding
        manifest["final_registry"] = {
            "URLS_USED": sorted(run_seen_urls),
            "STATS_USED": sorted(run_seen_stats_exact),
            "INSIGHTS_USED": sorted(run_seen_ins_exact),
            "STATS_FINGERPRINTS_USED": sorted(run_seen_statfp),
            "INSIGHTS_FINGERPRINTS_USED": sorted(run_seen_insfp),
            "ACRONYMS_SEEN": sorted(run_seen_acros),
        }
        manifest["updated_at"] = now_iso()
        supabase_write_textjson(paths["manifest"], manifest)

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
