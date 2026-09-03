#!/usr/bin/env python3
"""Rank the digest's focus rotation by search demand, and suggest additions.

Topic wording drives PubMed yield here, and the rotation is edited by hand in
config/digest_config.json. This script does not edit it. It reports which
topics are gaining or losing search interest and which related queries are
rising, so the next manual edit is informed rather than a guess.

    python scripts/topic_demand.py                  # report to stdout + outputs/
    python scripts/topic_demand.py --seeds "senior health,elderly health"

Requires SERPAPI_API_KEY. Without it the script exits cleanly, saying so.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "digest_config.json"
OUTPUT_DIR = REPO_ROOT / "outputs"

BASE = "https://serpapi.com/search"
GEO = "US"
DATE_WINDOW = "today 12-m"
BATCH_SIZE = 5           # SerpAPI compares at most five terms per TIMESERIES call
RECENT_POINTS = 8
MIN_SIGNAL = 3.0         # below this the 0-100 index is noise, not interest
DEFAULT_SEEDS = ["senior health", "elderly health", "older adult health"]
TIMEOUT = 30
RETRIES = 2


def serp_get(params: dict) -> dict | None:
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return None
    url = BASE + "?" + urllib.parse.urlencode({**params, "api_key": key})
    label = params.get("data_type", params.get("engine", "serpapi"))
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"SerpAPI timeout ({label})", file=sys.stderr)
            return None
        except Exception as exc:
            print(f"SerpAPI error ({label}): {str(exc)[:160]}", file=sys.stderr)
            return None
        # SerpAPI answers 200 with an {"error": ...} body for a spent quota.
        if isinstance(data, dict) and data.get("error"):
            print(f"SerpAPI error ({label}): {str(data['error'])[:160]}", file=sys.stderr)
            return None
        return data
    return None


def trend_from_timeline(timeline: list[dict], index: int) -> dict | None:
    values = []
    for point in timeline:
        if point.get("partial_data"):      # incomplete period; reads as a crash
            continue
        series = point.get("values") or []
        if index >= len(series):
            continue
        extracted = series[index].get("extracted_value")
        if isinstance(extracted, (int, float)):
            values.append(float(extracted))
    if len(values) < RECENT_POINTS * 2:
        return None
    recent = values[-RECENT_POINTS:]
    prior = values[-RECENT_POINTS * 2:-RECENT_POINTS]
    recent_mean = sum(recent) / len(recent)
    prior_mean = sum(prior) / len(prior)
    if recent_mean < MIN_SIGNAL and prior_mean < MIN_SIGNAL:
        return None
    change = ((recent_mean - prior_mean) / prior_mean * 100) if prior_mean >= 1 else 0.0
    return {"recent_mean": round(recent_mean, 1), "prior_mean": round(prior_mean, 1),
            "change_pct": round(change, 1), "peak": round(max(values), 1)}


def measure_topics(topics: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for start in range(0, len(topics), BATCH_SIZE):
        group = topics[start:start + BATCH_SIZE]
        data = serp_get({"engine": "google_trends", "q": ",".join(group),
                         "data_type": "TIMESERIES", "date": DATE_WINDOW,
                         "geo": GEO, "hl": "en"})
        if not data:
            continue
        timeline = (data.get("interest_over_time") or {}).get("timeline_data") or []
        for index, topic in enumerate(group):
            trend = trend_from_timeline(timeline, index)
            if trend:
                out[topic] = trend
    return out


def rising_queries(seeds: list[str], limit: int = 12) -> list[dict]:
    """Rising related queries around the beat's umbrella terms."""
    found: dict[str, dict] = {}
    for seed in seeds:
        data = serp_get({"engine": "google_trends", "q": seed,
                         "data_type": "RELATED_QUERIES", "date": DATE_WINDOW,
                         "geo": GEO, "hl": "en"})
        if not data:
            continue
        for entry in ((data.get("related_queries") or {}).get("rising") or []):
            query = (entry.get("query") or "").strip().lower()
            if not query or query in found:
                continue
            found[query] = {"query": query, "seed": seed,
                            "value": entry.get("value"),
                            "extracted_value": entry.get("extracted_value")}
    ranked = sorted(found.values(),
                    key=lambda r: r.get("extracted_value") or 0, reverse=True)
    return ranked[:limit]


def render(rotation: dict[str, dict], suggestions: list[dict], missing: list[str]) -> str:
    lines = [
        "# Topic demand for the focus rotation",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Google Trends, geo {GEO}, window {DATE_WINDOW}. Values are Google's relative "
        "0-100 interest index, not search counts — a large percentage rise from a low "
        "base is still a low base.",
        "",
        "## Current rotation, by change in search interest",
        "",
        "| Topic | Recent | Prior | Change | Peak |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for topic, t in sorted(rotation.items(), key=lambda kv: kv[1]["change_pct"], reverse=True):
        lines.append(f"| {topic} | {t['recent_mean']} | {t['prior_mean']} | "
                     f"{t['change_pct']:+.1f}% | {t['peak']} |")
    if missing:
        lines += ["", f"No usable signal for: {', '.join(missing)} — either below the "
                      f"noise floor of {MIN_SIGNAL} or too few complete data points.", ""]
    lines += ["", "## Rising related queries", "",
              "Candidates for the rotation. Check each against PubMed yield before adding: "
              "a term people search is not necessarily a term that indexes well.", ""]
    if suggestions:
        lines += ["| Query | Seed | Rise |", "| --- | --- | ---: |"]
        lines += [f"| {s['query']} | {s['seed']} | {s.get('value') or '—'} |" for s in suggestions]
    else:
        lines.append("None returned.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", default=",".join(DEFAULT_SEEDS),
                        help="Comma-separated umbrella terms for rising-query discovery.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    if not os.environ.get("SERPAPI_API_KEY", "").strip():
        print("SERPAPI_API_KEY is not set; nothing to do.", file=sys.stderr)
        return 0

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    topics = [t for t in (config.get("focus_rotation") or []) if t.strip()]
    if not topics:
        print("No topics in focus_rotation.", file=sys.stderr)
        return 0

    measured = measure_topics(topics)
    missing = [t for t in topics if t not in measured]
    suggestions = rising_queries([s.strip() for s in args.seeds.split(",") if s.strip()])

    report = render(measured, suggestions, missing)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "topic-demand.md").write_text(report, encoding="utf-8")
    (out / "topic-demand.json").write_text(
        json.dumps({"generated_at": datetime.now(UTC).isoformat(), "geo": GEO,
                    "window": DATE_WINDOW, "rotation": measured,
                    "no_signal": missing, "rising_queries": suggestions},
                   indent=2, sort_keys=True), encoding="utf-8")
    print(report)
    print(f"Wrote {out / 'topic-demand.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
