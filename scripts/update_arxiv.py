#!/usr/bin/env python3
import datetime as dt
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
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
DEFAULT_MAX_RESULTS = 80
DEFAULT_TOP_N = 20
DEFAULT_MAX_AUTHORS = 3


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
        if kw.lower() in hay:
            matched.append(kw)
            score += 3 if kw.lower() in title.lower() else 2
    if any(x in hay for x in ["gravitational-wave", "ligo", "virgo", "kagra"]):
        score += 2
    if "black hole" in hay:
        score += 1
    return score, matched


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


def parse(xml_bytes, keywords, top_n, max_authors):
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
        if raw_score == 0:
            continue
        papers.append(
            {
                "id": base_id,
                "title": title,
                "authors": authors,
                "authors_short": short_authors(authors, max_authors),
                "category": category,
                "abstract": abstract,
                "matches": matched,
                "relevance": relevance(raw_score),
                "base_score": raw_score,
            }
        )
    papers.sort(key=lambda p: (p["base_score"], p["id"]), reverse=True)
    return papers[:top_n]


def synthesize_with_openai(paper, watch):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    system = (
        "You are curating arXiv papers for a researcher. Use only the supplied metadata. "
        "Be concise and technical. Return strict JSON only."
    )
    user = {
        "watch": {
            "label": watch["label"],
            "prioritize": watch.get("prioritize", []),
            "deprioritize": watch.get("deprioritize", []),
            "notes": watch.get("notes", []),
        },
        "paper": {
            "title": paper["title"],
            "authors": paper["authors"],
            "arxiv_id": paper["id"],
            "category": paper["category"],
            "abstract": paper["abstract"],
        },
        "return_schema": {
            "one_sentence_summary": "string",
            "technical_bullets": ["string", "string"],
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


def merge_synthesis(paper, synth):
    if not synth:
        paper["summary"] = paper["abstract"]
        paper["technical_bullets"] = [
            f"Matched keywords: {', '.join(paper['matches']) or 'none recorded'}.",
            f"Primary category: {paper['category']}."
        ]
        paper["worth_reading_full"] = paper["relevance"] >= 4
        return paper
    paper["summary"] = synth.get("one_sentence_summary", paper["abstract"])
    bullets = synth.get("technical_bullets", [])[:2]
    while len(bullets) < 2:
        bullets.append("No extra technical note provided.")
    paper["technical_bullets"] = bullets
    paper["relevance"] = max(1, min(5, int(synth.get("relevance_score", paper["relevance"]))))
    paper["worth_reading_full"] = bool(synth.get("worth_reading_full", paper["relevance"] >= 4))
    return paper


def process_watch(watch, cache, display):
    categories = dedupe_keep_order(watch.get("categories", []))
    keywords = dedupe_keep_order(watch.get("keywords", []))
    max_results = display.get("max_results", DEFAULT_MAX_RESULTS)
    top_n = display.get("top_n", DEFAULT_TOP_N)
    max_authors = display.get("max_authors", DEFAULT_MAX_AUTHORS)

    xml = query_arxiv(categories, keywords, max_results)
    papers = parse(xml, keywords, top_n, max_authors)
    enriched = []

    for paper in papers:
        cache_key = f"{watch['id']}::{paper['id']}"
        cached = cache.get(cache_key)
        if cached:
            for key in ["summary", "technical_bullets", "relevance", "worth_reading_full"]:
                if key in cached:
                    paper[key] = cached[key]
            enriched.append(paper)
            continue
        synth = synthesize_with_openai(paper, watch)
        paper = merge_synthesis(paper, synth)
        cache[cache_key] = {
            "summary": paper["summary"],
            "technical_bullets": paper["technical_bullets"],
            "relevance": paper["relevance"],
            "worth_reading_full": paper["worth_reading_full"],
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
    cache = load_json(CACHE, {})
    display = prefs.get("display", {})
    watches = prefs.get("watches", [])

    watch_results = [process_watch(watch, cache, display) for watch in watches]

    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "display": {
            "max_authors": display.get("max_authors", DEFAULT_MAX_AUTHORS),
            "top_n": display.get("top_n", DEFAULT_TOP_N),
            "max_results": display.get("max_results", DEFAULT_MAX_RESULTS),
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
