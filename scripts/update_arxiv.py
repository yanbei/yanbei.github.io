#!/usr/bin/env python3
import datetime as dt
import io
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "arxiv.json"
OUT_JS = ROOT / "data" / "arxiv.js"
CACHE = ROOT / "data" / "arxiv_cache.json"
PREFS = ROOT / "config" / "preferences.json"
PROFILE = ROOT / "config" / "yanbei_profile.json"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
DEFAULT_MAX_RESULTS = 80
DEFAULT_TOP_N = 20
DEFAULT_MAX_AUTHORS = 3
DEFAULT_RECENT_DAYS = 7
DEFAULT_PDF_MAX_PAGES = 6
DEFAULT_PDF_MAX_CHARS = 30000


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def text(el, path, default=""):
    found = el.find(path, NS)
    if found is None or found.text is None:
        return default
    return " ".join(found.text.split())


def dedupe_keep_order(items):
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def pdf_url(arxiv_id):
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def extract_pdf_text(url, max_pages, max_chars):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        reader = PdfReader(io.BytesIO(data))
        chunks = []
        for page in reader.pages[:max_pages]:
            chunks.append((page.extract_text() or "").strip())
            joined = "\n\n".join(chunks)
            if len(joined) >= max_chars:
                return joined[:max_chars]
        joined = "\n\n".join(chunks).strip()
        return joined[:max_chars] if joined else None
    except Exception:
        return None


def query_arxiv(categories, keywords, max_results):
    query = "({}) AND ({})".format(
        " OR ".join(f"cat:{c}" for c in categories),
        " OR ".join(f'all:"{k}"' if (" " in k or "-" in k) else f"all:{k}" for k in keywords),
    )
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def score_entry(title, summary, keywords):
    hay = f"{title} {summary}".lower()
    score = 0
    matched = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in hay:
            matched.append(kw)
            score += 3 if kw_lower in title.lower() else 2
    if any(x in hay for x in ["gravitational-wave", "ligo", "virgo", "kagra"]):
        score += 2
    if "black hole" in hay:
        score += 1
    return score, matched


def profile_score(title, summary, profile):
    hay = f"{title} {summary}".lower()
    score = 0
    previous_hits = []
    interest_hits = []
    for item in profile.get("previous_work", []):
        if item.lower() in hay:
            previous_hits.append(item)
            score += 2
    for item in profile.get("expertise", []):
        if item.lower() in hay:
            interest_hits.append(item)
            score += 2
    return score, previous_hits, interest_hits


def relevance(score):
    if score >= 10:
        return 5
    if score >= 8:
        return 4
    if score >= 6:
        return 3
    if score >= 4:
        return 2
    return 1


def short_authors(authors, max_authors):
    if len(authors) <= max_authors:
        return authors
    return authors[:max_authors] + [f"et al. ({len(authors)} authors)"]


def published_datetime(entry):
    published = text(entry, "a:published")
    if not published:
        return None
    return dt.datetime.fromisoformat(published.replace("Z", "+00:00"))


def recency_bonus(published_at, recent_days):
    if not published_at:
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    age = (now - published_at).total_seconds() / 86400.0
    if age <= recent_days:
        return 4
    if age <= 14:
        return 2
    if age <= 30:
        return 1
    return 0


def age_days(published_at):
    if not published_at:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    return round((now - published_at).total_seconds() / 86400.0, 1)


def parse(xml_bytes, keywords, top_n, max_authors, recent_days, profile):
    root = ET.fromstring(xml_bytes)
    papers = []
    seen = set()
    for entry in root.findall("a:entry", NS):
        arxiv_id = text(entry, "a:id").split("/")[-1]
        base_id = arxiv_id.split("v")[0]
        if base_id in seen:
            continue
        seen.add(base_id)
        title = text(entry, "a:title")
        abstract = text(entry, "a:summary")
        authors = [text(a, "a:name") for a in entry.findall("a:author", NS)]
        primary = entry.find("arxiv:primary_category", NS)
        category = primary.attrib.get("term", "") if primary is not None else ""
        raw_score, matched = score_entry(title, abstract, keywords)
        profile_boost, previous_hits, interest_hits = profile_score(title, abstract, profile)
        if raw_score == 0 and profile_boost == 0:
            continue
        published_at = published_datetime(entry)
        final_score = raw_score + profile_boost + recency_bonus(published_at, recent_days)
        papers.append(
            {
                "id": base_id,
                "title": title,
                "authors": authors,
                "authors_short": short_authors(authors, max_authors),
                "category": category,
                "abstract": abstract,
                "pdf_url": pdf_url(base_id),
                "matches": matched,
                "published": published_at.isoformat() if published_at else "",
                "age_days": age_days(published_at),
                "previous_work_hits": previous_hits,
                "current_interest_hits": interest_hits,
                "used_openai": False,
                "used_pdf_text": False,
                "pdf_text_chars": 0,
                "relevance": relevance(final_score),
                "base_score": final_score,
            }
        )
    papers.sort(key=lambda p: (p["base_score"], p["published"], p["id"]), reverse=True)
    return papers[:top_n]


def synthesize_with_openai(paper, watch, profile, pdf_text):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    system = (
        "You are curating arXiv papers for Yanbei Chen. Prefer the supplied PDF excerpt over the abstract when available. "
        "Return exactly three bullets in strict JSON. "
        "Bullet 1 must be exactly three sentences summarizing the scientific content and novelty of the paper, using the PDF excerpt when present. "
        "Bullet 2 must explain why Yanbei would care, grounding the explanation in his previous work and current interests when relevant. "
        "Bullet 3 must list key words/topics and mention when it was published or how recent it is."
    )
    user = {
        "watch": {
            "label": watch["label"],
            "prioritize": watch.get("prioritize", []),
            "deprioritize": watch.get("deprioritize", []),
            "notes": watch.get("notes", []),
        },
        "yanbei_profile": {
            "previous_work": profile.get("previous_work", []),
            "current_interest": profile.get("expertise", []),
        },
        "paper": {
            "title": paper["title"],
            "authors": paper["authors"],
            "arxiv_id": paper["id"],
            "category": paper["category"],
            "abstract": paper["abstract"],
            "pdf_url": paper.get("pdf_url", ""),
            "pdf_excerpt": pdf_text or "",
            "published": paper.get("published", ""),
            "age_days": paper.get("age_days"),
            "previous_work_hits": paper.get("previous_work_hits", []),
            "current_interest_hits": paper.get("current_interest_hits", []),
            "keyword_hits": paper.get("matches", []),
        },
        "return_schema": {
            "summary_bullets": ["string", "string", "string"],
            "relevance_score": "integer 1-5",
            "worth_reading_full": "boolean"
        }
    }
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    )
    text_out = getattr(response, "output_text", "") or ""
    return json.loads(text_out)


def merge_synthesis(paper, synth, watch, profile):
    if not synth:
        age_note = f"published about {paper['age_days']} days ago" if paper.get("age_days") is not None else "publication date unavailable"
        previous = ", ".join(paper.get("previous_work_hits") or profile.get("previous_work", [])[:2])
        current = ", ".join(paper.get("current_interest_hits") or profile.get("expertise", [])[:2])
        why_parts = [part for part in [previous, current] if part]
        why_text = "; and also to ".join(why_parts) if why_parts else watch.get("label", "this topic")
        novelty_hint = "The apparent novelty is inferred only from the abstract/title metadata because PDF summarization was unavailable."
        paper["summary_bullets"] = [
            f"This paper studies {paper['title']} using the methods and problem setup described in the abstract. Its scientific content appears to center on {paper['category']} themes highlighted by the metadata. {novelty_hint}",
            f"Yanbei may care because it connects to his previous work and current interests, especially {why_text}.",
            f"Key words/topics: {', '.join(paper['matches']) or 'none recorded'}; {age_note}."
        ]
        paper["used_openai"] = False
        paper["worth_reading_full"] = paper["relevance"] >= 4
        return paper
    bullets = synth.get("summary_bullets", [])[:3]
    while len(bullets) < 3:
        bullets.append("No extra technical note provided.")
    paper["summary_bullets"] = bullets
    paper["used_openai"] = True
    paper["relevance"] = max(1, min(5, int(synth.get("relevance_score", paper["relevance"]))))
    paper["worth_reading_full"] = bool(synth.get("worth_reading_full", paper["relevance"] >= 4))
    return paper


def process_watch(watch, cache, display, profile):
    categories = dedupe_keep_order(watch.get("categories", []))
    keywords = dedupe_keep_order(watch.get("keywords", []))
    max_results = display.get("max_results", DEFAULT_MAX_RESULTS)
    top_n = display.get("top_n", DEFAULT_TOP_N)
    max_authors = display.get("max_authors", DEFAULT_MAX_AUTHORS)
    recent_days = display.get("recent_days", DEFAULT_RECENT_DAYS)
    pdf_max_pages = display.get("pdf_max_pages", DEFAULT_PDF_MAX_PAGES)
    pdf_max_chars = display.get("pdf_max_chars", DEFAULT_PDF_MAX_CHARS)

    xml = query_arxiv(categories, keywords, max_results)
    papers = parse(xml, keywords, top_n, max_authors, recent_days, profile)
    enriched = []

    for paper in papers:
        cache_key = f"{watch['id']}::{paper['id']}"
        cached = cache.get(cache_key)
        if cached:
            for key in ["summary_bullets", "relevance", "worth_reading_full", "used_openai", "used_pdf_text", "pdf_text_chars"]:
                if key in cached:
                    paper[key] = cached[key]
            enriched.append(paper)
            continue
        pdf_text = extract_pdf_text(paper.get("pdf_url", ""), pdf_max_pages, pdf_max_chars)
        paper["used_pdf_text"] = bool(pdf_text)
        paper["pdf_text_chars"] = len(pdf_text) if pdf_text else 0
        synth = synthesize_with_openai(paper, watch, profile, pdf_text)
        paper = merge_synthesis(paper, synth, watch, profile)
        cache[cache_key] = {
            "summary_bullets": paper["summary_bullets"],
            "relevance": paper["relevance"],
            "worth_reading_full": paper["worth_reading_full"],
            "used_openai": paper.get("used_openai", False),
            "used_pdf_text": paper.get("used_pdf_text", False),
            "pdf_text_chars": paper.get("pdf_text_chars", 0),
        }
        enriched.append(paper)

    return {
        "id": watch["id"],
        "label": watch["label"],
        "categories": categories,
        "keywords": keywords,
        "papers": enriched,
    }


def main():
    prefs = load_json(PREFS, {})
    profile = load_json(PROFILE, {})
    cache = load_json(CACHE, {})
    display = prefs.get("display", {})
    watches = prefs.get("watches", [])

    watch_results = [process_watch(watch, cache, display, profile) for watch in watches]

    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "display": {
            "max_authors": display.get("max_authors", DEFAULT_MAX_AUTHORS),
            "top_n": display.get("top_n", DEFAULT_TOP_N),
            "max_results": display.get("max_results", DEFAULT_MAX_RESULTS),
            "recent_days": display.get("recent_days", DEFAULT_RECENT_DAYS),
            "pdf_max_pages": display.get("pdf_max_pages", DEFAULT_PDF_MAX_PAGES),
            "pdf_max_chars": display.get("pdf_max_chars", DEFAULT_PDF_MAX_CHARS),
        },
        "watches": watch_results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    OUT.write_text(json_text + "\n")
    OUT_JS.write_text("window.ARXIV_DATA = " + json_text + ";\n", encoding="utf-8")
    CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {sum(len(w['papers']) for w in watch_results)} papers across {len(watch_results)} watches to {OUT}")


if __name__ == "__main__":
    main()
