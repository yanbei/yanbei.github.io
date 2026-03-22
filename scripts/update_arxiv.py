#!/usr/bin/env python3
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CATEGORIES = ["gr-qc", "hep-th", "astro-ph.HE"]
KEYWORDS = [
    "quasinormal mode",
    "qnm",
    "teukolsky",
    "black hole perturbation",
    "ringdown",
    "kerr",
    "gravitational-wave memory",
    "modified gravity",
    "quantum gravity signatures",
]
MAX_RESULTS = 40
TOP_N = 12

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "arxiv.json"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def query_arxiv():
    query = "({}) AND ({})".format(
        " OR ".join(f"cat:{c}" for c in CATEGORIES),
        " OR ".join(f'all:"{k}"' if (" " in k or "-" in k) else f"all:{k}" for k in KEYWORDS),
    )
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": MAX_RESULTS,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def text(el, path, default=""):
    found = el.find(path, NS)
    if found is None or found.text is None:
        return default
    return " ".join(found.text.split())


def score_entry(title, summary):
    hay = f"{title} {summary}".lower()
    score = 0
    matched = []
    for kw in KEYWORDS:
        if kw in hay:
            matched.append(kw)
            score += 3 if kw in title.lower() else 2
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


def parse(xml_bytes):
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
        summary = text(entry, "a:summary")
        authors = [text(a, "a:name") for a in entry.findall("a:author", NS)]
        primary = entry.find("arxiv:primary_category", NS)
        category = primary.attrib.get("term", "") if primary is not None else ""
        raw_score, matched = score_entry(title, summary)
        if raw_score == 0:
            continue
        papers.append(
            {
                "id": base_id,
                "title": title,
                "authors": authors,
                "category": category,
                "summary": summary,
                "matches": matched,
                "relevance": relevance(raw_score),
                "score": raw_score,
            }
        )
    papers.sort(key=lambda p: (p["score"], p["id"]), reverse=True)
    return papers[:TOP_N]


def main():
    xml = query_arxiv()
    papers = parse(xml)
    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "categories": CATEGORIES,
        "keywords": [
            "quasinormal mode",
            "QNM",
            "Teukolsky",
            "black hole perturbation",
            "ringdown",
            "Kerr",
            "gravitational-wave memory",
            "modified gravity",
            "quantum gravity signatures",
        ],
        "papers": papers,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(papers)} papers to {OUT}")


if __name__ == "__main__":
    main()
