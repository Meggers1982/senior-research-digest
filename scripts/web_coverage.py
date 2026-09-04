"""Has the consumer press already written up these studies?

Answers the one question that decides whether a pitch is still open, and feeds
the outlet suggestions so a story is never pitched to the publication that just
ran it.

Google News ranks by topical relevance, so a query about a grip-strength study
returns anything about grip strength. Results are therefore filtered on
headline overlap with the study title -- the same guard
agingwire-research-intelligence needed after its first live run reported 12 of
13 items as widely covered.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib.parse import urlparse

BASE = "https://serpapi.com/search"
TIMEOUT = 25
RETRIES = 1
DEFAULT_TOP_N = 8          # studies checked per run, highest-numbered first
RECENCY = "when:90d"       # digests cover a 90-day window
MAX_QUERY_WORDS = 10

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "be", "this", "that", "new",
    "may", "can", "could", "older", "adults", "senior", "seniors", "aging", "study",
}
JACCARD_FLOOR = 0.18
SHARED_MIN = 3
SHARED_RATIO = 0.35


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in STOP}


def title_similar(left: str, right: str) -> bool:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False
    shared = a & b
    if len(shared) / len(a | b) >= JACCARD_FLOOR:
        return True
    return len(shared) >= SHARED_MIN and len(shared) / min(len(a), len(b)) >= SHARED_RATIO


def build_query(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", re.sub(r"\([^)]*\)", " ", title or ""))
    words = [w for w in cleaned.split() if len(w) > 2 and w.lower() not in STOP]
    return " ".join(words[:MAX_QUERY_WORDS])


def _serp(params: dict) -> dict | None:
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return None
    url = BASE + "?" + urllib.parse.urlencode({**params, "api_key": key})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            if attempt < RETRIES:
                time.sleep(2)
                continue
            return None
        except Exception as exc:
            print(f"  SerpAPI error: {str(exc)[:120]}", file=sys.stderr)
            return None
        # SerpAPI answers 200 with an {"error": ...} body for a spent quota.
        if isinstance(data, dict) and data.get("error"):
            print(f"  SerpAPI: {str(data['error'])[:120]}", file=sys.stderr)
            return None
        return data
    return None


def check_study(title: str) -> dict | None:
    query = build_query(title)
    if not query:
        return None
    data = _serp({"engine": "google_news", "q": f"{query} {RECENCY}",
                  "gl": "us", "hl": "en"})
    if data is None:
        return None
    outlets, samples, returned = [], [], 0
    for article in (data.get("news_results") or [])[:20]:
        headline = (article.get("title") or "").strip()
        link = (article.get("link") or "").strip()
        if not headline or not link:
            continue
        returned += 1
        if not title_similar(title, headline):
            continue
        name = ((article.get("source") or {}).get("name")
                or urlparse(link).netloc.lower().removeprefix("www.")).strip()
        if name and name not in outlets:
            outlets.append(name)
            samples.append({"title": headline[:200], "outlet": name, "link": link})
    return {"query": query, "returned": returned, "outlets": outlets,
            "articles": samples[:3],
            "state": "unreported" if not outlets
                     else "lightly_reported" if len(outlets) <= 2 else "widely_reported"}


# The digest exists only as markdown at this point; study headlines are the
# "### 1. Headline" lines written by digest_generator.
_HEADING = re.compile(r"^###\s*\d+\.\s*(.+?)\s*$", re.M)


def titles_from_digest(markdown: str) -> list[str]:
    return [t.strip() for t in _HEADING.findall(markdown or "") if t.strip()]


def check_digest(titles: list[str], top_n: int = DEFAULT_TOP_N) -> dict:
    """Check the leading studies and collect the outlets already on them."""
    if not os.environ.get("SERPAPI_API_KEY", "").strip():
        return {"checked": 0, "skipped_reason": "SERPAPI_API_KEY is not set",
                "outlets": set(), "by_study": {}}
    checked, covered, by_study = 0, set(), {}
    for raw in titles[:top_n]:
        title = (raw or "").strip()
        if not title:
            continue
        result = check_study(title)
        if result is None:
            continue
        checked += 1
        by_study[title] = result
        covered.update(result["outlets"])
    return {"checked": checked, "outlets": covered, "by_study": by_study}
