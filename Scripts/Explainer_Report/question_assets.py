# Scripts/Explainer_Report/question_assets.py

import os
import re
import json
import uuid
import time
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

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

# Continuity window for de-duplication pressure
MAX_QA_IN_CONTEXT = int(os.getenv("EXPLAINER_MAX_QA_IN_CONTEXT", "12"))
MAX_CONTEXT_CHARS = int(os.getenv("EXPLAINER_MAX_CONTEXT_CHARS", "16000"))

# Preferred medical domains (soft allow-list; we still accept others if valid)
ALLOWED_DOMAINS = {
    "www.nhs.uk", "nhs.uk", "www.nice.org.uk", "nice.org.uk",
    "www.bmj.com", "bmj.com", "www.jamanetwork.com", "jamanetwork.com",
    "www.nejm.org", "nejm.org", "www.cdc.gov", "cdc.gov",
    "www.who.int", "who.int", "www.cochranelibrary.com", "cochranelibrary.com"
}

# Disallowed URL signatures (to block downloads)
BAD_URL_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
BAD_URL_SNIPPETS = ("/pdf/", "/download", "?download=")

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
    # Remove markdown links first (keep visible anchor text)
    def _strip_md(m):
        inner = m.group(0)
        # remove the (url) part
        inner = re.sub(r'\(\s*https?://[^)]+\)', '', inner)
        return inner.replace("[]", "").strip()
    text = MD_LINK_RE.sub(_strip_md, text)
    # Remove raw URLs
    text = URL_RE.sub('', text)
    # Normalize spaces
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

def normalise_bullets(s: str) -> str:
    if not isinstance(s, str):
        return s
    # Split by sentence endings into fragments
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', s) if p.strip()]
    # Expand by splitting on ';' or ':' if needed
    while len(parts) < 4 and any((';' in x or ':' in x) for x in parts):
        idx = next(i for i,x in enumerate(parts) if (';' in x or ':' in x))
        frag = parts.pop(idx)
        if ';' in frag:
            a, b = frag.split(';', 1)
        else:
            a, b = frag.split(':', 1)
        parts[idx:idx] = [a.strip() + '.', b.strip() + '.']
    # Pad with empties if still short
    while len(parts) < 4:
        parts.append('')
    parts = parts[:4]
    # Ensure punctuation and join with newlines
    parts = [p if p.endswith(('.', '!', '?')) else (p + '.') for p in parts]
    return "\n".join(parts)

def fingerprint(text: str) -> str:
    t = (text or '').lower()
    t = re.sub(r'\d+(\.\d+)?%?', 'X', t)
    t = re.sub(r'\s+', '', t)
    return t[:160]

def build_seen_sets(history: List[str]) -> Tuple[set, set, set]:
    seen_urls, seen_statfp, seen_insfp = set(), set(), set()
    for s in history[-MAX_QA_IN_CONTEXT:]:
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        # URLs
        ra = obj.get("Related Article") or {}
        u = (ra.get("Related Article URL") or "").strip()
        if u:
            seen_urls.add(u)
        # Stat/Insight fingerprints
        st = obj.get("Statistic") or ""
        ins = obj.get("Insight") or ""
        if st:
            seen_statfp.add(fingerprint(st))
        if ins:
            seen_insfp.add(fingerprint(ins))
    return seen_urls, seen_statfp, seen_insfp

def sanitise_and_validate(obj: Dict[str, Any], history: List[str]) -> Dict[str, Any]:
    # Strip any links from non-article fields
    for fld in ("Summary", "Bullet Points", "Statistic", "Insight", "Header", "Sub-Header", "Question"):
        if fld in obj:
            obj[fld] = strip_links(obj[fld])

    # Normalise bullets to exactly 4 sentences
    if "Bullet Points" in obj:
        obj["Bullet Points"] = normalise_bullets(obj["Bullet Points"])

    # Enforce uniqueness for Stat/Insight using near-dup fingerprints vs history
    seen_urls, seen_statfp, seen_insfp = build_seen_sets(history)

    stp = fingerprint(obj.get("Statistic", ""))
    inp = fingerprint(obj.get("Insight", ""))

    if stp in seen_statfp:
        raise ValueError("Statistic duplicates a previous item (near-duplicate fingerprint).")
    if inp in seen_insfp:
        raise ValueError("Insight duplicates a previous item (near-duplicate fingerprint).")

    # Validate article URL
    ra = obj.get("Related Article") or {}
    url = (ra.get("Related Article URL") or "").strip()
    if is_bad_article_url(url):
        raise ValueError(f"Related Article URL is a download or invalid: {url}")
    if url in seen_urls:
        raise ValueError(f"Related Article URL duplicates a previous item: {url}")

    # Soft preference for allowed domains (do not fail; just annotate)
    host = hostname(url)
    if host and ALLOWED_DOMAINS and host not in ALLOWED_DOMAINS:
        ra["_note"] = f"Non-preferred domain ({host}); verify credibility."

    obj["Related Article"] = ra
    return obj

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

        history: List[str] = []

        for idx, q_tmpl in enumerate(q_templates):
            if idx <= ckpt["last_completed_index"]:
                continue

            filled_q = format_question(q_tmpl, ctx)
            mapping = {k: safe_escape_braces(str(v)) for k, v in ctx.items()}
            mapping["question"] = safe_escape_braces(filled_q)

            prior_block = build_prior_context(history)
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

            # Try up to 2 full generations for URL/uniqueness violations
            gen_attempts = 2
            for attempt in range(1, gen_attempts + 1):
                try:
                    t0 = time.time()
                    obj = call_openai(prompt, model=DEFAULT_MODEL, temperature=TEMPERATURE)
                    obj = sanitise_and_validate(obj, history)
                    elapsed = round(time.time() - t0, 3)

                    # Persist output
                    supabase_write_txt(outfile, json.dumps(obj, ensure_ascii=False, indent=2))

                    item_meta.update({"status": "done", "completed_at": now_iso(), "latency_seconds": elapsed})
                    supabase_write_textjson(paths["manifest"], manifest)

                    # Advance checkpoint and grow history
                    ckpt.update({"last_completed_index": idx, "updated_at": now_iso()})
                    supabase_write_textjson(paths["checkpoint"], ckpt)
                    history.append(json.dumps(obj, ensure_ascii=False))

                    time.sleep(0.25)
                    break

                except Exception as e:
                    if attempt >= gen_attempts:
                        item_meta.update({"status": "failed", "failed_at": now_iso(), "error": str(e)})
                        supabase_write_textjson(paths["manifest"], manifest)
                        logger.error(f"❌ Generation failed for q_id={q_id}: {e}")
                    else:
                        logger.warning(f"🔁 Regenerating q_id={q_id} due to: {e}")

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
