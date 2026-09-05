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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

BASE = "https://serpapi.com/search"
TIMEOUT = 25
RETRIES = 2
RETRY_STATUS = {429, 500, 502, 503, 504}
PAUSE_SECONDS = 0.4        # the SerpAPI quota is shared with two other repos
DEFAULT_DAYS_BACK = 90     # overridden by digest_config.json's days_back
MAX_QUERY_WORDS = 10

# Every study in the digest is checked, not just the first few, but a runaway
# digest should not be able to drain a shared quota in one run.
MAX_CHECKS_PER_RUN = 40

CACHE_PATH = Path(__file__).parent.parent / "state" / "coverage_cache.json"
# Coverage is not static -- an unreported study can be picked up next week -- but
# the 90-day PubMed window means the same study recurs across many daily runs.
# Two weeks keeps the state honest while collapsing almost all of the cost.
CACHE_TTL_DAYS = 14

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
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except urllib.error.HTTPError as exc:
            # A rate limit or a bad gateway is worth another try; a 4xx is not.
            if exc.code in RETRY_STATUS and attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  SerpAPI HTTP {exc.code}", file=sys.stderr)
            return None
        except urllib.error.URLError as exc:
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  SerpAPI unreachable: {str(exc.reason)[:100]}", file=sys.stderr)
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


def check_study(title: str, days_back: int = DEFAULT_DAYS_BACK) -> dict | None:
    query = build_query(title)
    if not query:
        return None
    data = _serp({"engine": "google_news", "q": f"{query} when:{days_back}d",
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


# The digest exists only as markdown at this point; a study is a "### 1. Headline"
# line written by digest_generator, followed within a few lines by its PMID.
_STUDY = re.compile(
    r"^###\s*\d+\.\s*(?P<title>.+?)\s*$(?P<body>(?:\n(?!###).*)*)",
    re.M,
)
_PMID = re.compile(r"\*\*PMID:\*\*\s*(\d+)")


def titles_from_digest(markdown: str) -> list[str]:
    return [m.group("title").strip() for m in _STUDY.finditer(markdown or "")
            if m.group("title").strip()]


def studies_from_digest(markdown: str) -> list[tuple[str, str]]:
    """(pmid, title) for every study, so results can be joined to the study
    record rather than only to its headline text."""
    out = []
    for match in _STUDY.finditer(markdown or ""):
        title = match.group("title").strip()
        if not title:
            continue
        pmid = _PMID.search(match.group("body") or "")
        out.append((pmid.group(1) if pmid else "", title))
    return out


def _load_cache(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    fresh = {}
    for pmid, entry in (raw.get("studies") or {}).items():
        try:
            seen = datetime.fromisoformat(entry["checked_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if seen >= cutoff:
            fresh[pmid] = entry
    return fresh


def _save_cache(path: Path, studies: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"studies": studies}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"  coverage cache not written: {exc}", file=sys.stderr)


def check_digest(
    studies,
    days_back: int = DEFAULT_DAYS_BACK,
    cache_path: Path | None = CACHE_PATH,
    limit: int = MAX_CHECKS_PER_RUN,
) -> dict:
    """Check every study and collect the outlets already reporting them.

    Accepts either `[(pmid, title), ...]` or a plain list of titles. Results are
    cached by PMID: the PubMed window is 90 days wide and runs are daily, so the
    same study comes round many times and used to be re-queried at full price on
    each one.
    """
    if not os.environ.get("SERPAPI_API_KEY", "").strip():
        return {"checked": 0, "cached": 0, "skipped": 0,
                "skipped_reason": "SERPAPI_API_KEY is not set",
                "outlets": set(), "by_study": {}, "by_pmid": {}}

    pairs = [s if isinstance(s, (tuple, list)) else ("", s) for s in studies]
    cache = _load_cache(cache_path) if cache_path else {}

    checked = cached_hits = skipped = 0
    stored = False
    covered, by_study, by_pmid = set(), {}, {}

    for pmid, raw in pairs:
        title = (raw or "").strip()
        if not title:
            continue

        entry = cache.get(pmid) if pmid else None
        if entry and entry.get("result"):
            result = entry["result"]
            cached_hits += 1
        elif checked >= limit:
            # Out of budget for this run rather than out of studies. Recorded so
            # the dashboard can say the check was partial instead of implying
            # these studies came back clean.
            skipped += 1
            continue
        else:
            if checked:
                time.sleep(PAUSE_SECONDS)
            result = check_study(title, days_back=days_back)
            if result is None:
                skipped += 1
                continue
            checked += 1
            if pmid:
                cache[pmid] = {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "result": result,
                }
                stored = True

        by_study[title] = result
        if pmid:
            by_pmid[pmid] = result
        covered.update(result["outlets"])

    if cache_path and stored:
        _save_cache(cache_path, cache)

    return {"checked": checked, "cached": cached_hits, "skipped": skipped,
            "outlets": covered, "by_study": by_study, "by_pmid": by_pmid}
