"""Daily senior living research digest pipeline — entry point for GitHub Actions."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from journals import ISSNS
from pubmed import search_by_issns, fetch_summaries, fetch_abstracts_for_pmids
from digest_generator import generate_digest
from fact_checker import run_fact_check
import outlets as outlets_mod
import web_coverage
from trends import generate_trends_section
from build_dashboard_data import main as rebuild_dashboard_data


REPO_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs"
TOPIC_MEMORY_DIR = REPO_ROOT / "topic_memory"
CONFIG_PATH = REPO_ROOT / "config" / "digest_config.json"

# Rotating subject focuses — one is chosen each day by day-of-year.
# Set to an empty list (or "" in config) to search broadly every day.
DEFAULT_FOCUS_ROTATION = [
    "",                                  # Broad — all senior living topics
    "dementia",
    "falls",
    "cardiovascular disease",
    "depression",
    "nutrition",
    "sleep",
    "palliative care",
    "osteoporosis",
    "sarcopenia",
    "cognitive decline",
    "hearing loss",
    "vision loss",
    "polypharmacy",
]


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def pick_subject_focus(config: dict) -> str:
    """Pick today's subject focus.

    Priority:
      1. DIGEST_FOCUS env var (set by workflow_dispatch input)
      2. config["subject_focus"] if non-empty string
      3. config["focus_rotation"] list, rotated by day-of-year
      4. DEFAULT_FOCUS_ROTATION, rotated by day-of-year
    """
    override = os.environ.get("DIGEST_FOCUS", "").strip()
    if override:
        return override

    fixed = config.get("subject_focus", "").strip()
    if fixed:
        return fixed

    rotation = config.get("focus_rotation") or DEFAULT_FOCUS_ROTATION
    if not rotation:
        return ""

    day = datetime.now().timetuple().tm_yday
    focus = rotation[day % len(rotation)]
    print(f"Rotating focus #{day % len(rotation)}: '{focus or '(broad)'}'")
    return focus


def unique_output_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path
    stem, suffix, parent = base_path.stem, base_path.suffix, base_path.parent
    for n in range(2, 20):
        candidate = parent / f"{stem} (Part {n}){suffix}"
        if not candidate.exists():
            return candidate
    return base_path


def write_run_sidecar(digest_path: Path, coverage: dict, summaries: dict,
                      selected_pmids: list) -> None:
    """Per-run facts that never survive the trip through markdown.

    The digest is prose; the coverage state and PubMed's own metadata are not.
    Keeping them beside the digest means re-scoring the archive is just a
    dashboard rebuild, with no API calls at all.
    """
    wanted = set(selected_pmids or [])
    meta = {}
    for pmid, record in (summaries or {}).items():
        if wanted and pmid not in wanted:
            continue
        meta[pmid] = {
            "pubdate": record.get("pubdate", ""),
            "journal": record.get("fulljournalname") or record.get("source", ""),
        }
    payload = {
        "coverage_checked": coverage.get("checked", 0),
        "coverage_cached": coverage.get("cached", 0),
        "coverage_skipped": coverage.get("skipped", 0),
        "coverage_skipped_reason": coverage.get("skipped_reason", ""),
        "by_pmid": {
            pmid: {"state": result.get("state", ""),
                   "outlets": result.get("outlets", []),
                   "articles": result.get("articles", [])}
            for pmid, result in (coverage.get("by_pmid") or {}).items()
        },
        "pubmed": meta,
    }
    path = digest_path.with_name(digest_path.stem + ".coverage.json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    # ── Environment ──────────────────────────────────────────────────────────
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    ncbi_api_key = os.environ.get("NCBI_API_KEY") or None

    if not anthropic_api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")

    # ── Config ───────────────────────────────────────────────────────────────
    config = load_config()
    subject_focus = pick_subject_focus(config)
    primary_audience = config["primary_audience"]
    secondary_audience = config["secondary_audience"]
    days_back = config.get("days_back", 90)

    print(f"\n{'=' * 60}")
    print(f"Senior Living Digest Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Journals  : {len(ISSNS)} curated senior care journals")
    print(f"Focus     : {subject_focus or '(broad — all senior living topics)'}")
    print(f"Audience  : {primary_audience} / {secondary_audience}")
    print(f"{'=' * 60}\n")

    OUTPUTS_DIR.mkdir(exist_ok=True)

    # ── Step 1: Search PubMed by ISSN ────────────────────────────────────────
    print("Searching PubMed across all senior care journals...")
    pmids = search_by_issns(
        issns=ISSNS,
        days_back=days_back,
        subject_focus=subject_focus,
        max_per_batch=25,
        max_total=200,
        ncbi_api_key=ncbi_api_key,
    )
    print(f"Found {len(pmids)} article IDs")

    if not pmids:
        print("No articles found. Exiting.")
        sys.exit(0)

    # ── Step 2: Fetch summaries ───────────────────────────────────────────────
    # These used to be fetched and discarded. They are PubMed's own record of the
    # publication date and journal, so they now go into the run's sidecar as
    # better provenance than the model's transcription of the same fields.
    print("Fetching summaries...")
    summaries = fetch_summaries(pmids, ncbi_api_key=ncbi_api_key)
    print(f"Fetched {len(summaries)} summaries")

    # ── Step 3: Fetch abstracts (cap at 40) ───────────────────────────────────
    print("Fetching abstracts (up to 40)...")
    abstracts = fetch_abstracts_for_pmids(pmids[:40], ncbi_api_key=ncbi_api_key)
    print(f"Retrieved {len(abstracts)} abstracts with usable content")

    if not abstracts:
        print("No usable abstracts. Exiting.")
        sys.exit(0)

    # ── Step 4: Generate digest ───────────────────────────────────────────────
    print("\nGenerating digest...")
    digest_content, selected_pmids = generate_digest(
        subject_focus=subject_focus,
        primary_audience=primary_audience,
        secondary_audience=secondary_audience,
        abstracts=abstracts,
        journal_count=len(ISSNS),
        api_key=anthropic_api_key,
    )
    print(f"Digest generated — {len(selected_pmids)} studies selected")

    month_year = datetime.now().strftime("%B %Y")
    focus_tag = f" — {subject_focus.title()}" if subject_focus else ""
    digest_filename = f"Senior Living Research Digest{focus_tag} — {month_year}.md"
    digest_path = unique_output_path(OUTPUTS_DIR / digest_filename)

    # ── Step 5: Run fact checker ──────────────────────────────────────────────
    print("\nRunning fact checker...")
    fact_check_content = run_fact_check(
        digest_content=digest_content,
        selected_pmids=selected_pmids,
        ncbi_api_key=ncbi_api_key,
        anthropic_api_key=anthropic_api_key,
        subject_focus=subject_focus,
    )

    fact_check_filename = digest_path.stem + " Fact Check.md"
    fact_check_path = OUTPUTS_DIR / fact_check_filename
    fact_check_path.write_text(fact_check_content, encoding="utf-8")
    print(f"Fact check saved: outputs/{fact_check_path.name}")

    # ── Step 6: Compare against the prior digest on this topic ───────────────
    print("\nGenerating trends & continuity section...")
    # Which studies has the consumer press already written up? The outlets it
    # finds are excluded from the pitch suggestions below.
    coverage = web_coverage.check_digest(
        web_coverage.studies_from_digest(digest_content),
        days_back=days_back,
    )
    if coverage.get("skipped_reason"):
        print(f"Web coverage: skipped — {coverage['skipped_reason']}")
    else:
        already = coverage["outlets"]
        print(f"Web coverage: {coverage['checked']} checked, "
              f"{coverage['cached']} from cache, {coverage['skipped']} skipped; "
              f"{len(already)} outlet(s) already reporting"
              + (f" ({', '.join(sorted(already)[:5])})" if already else ""))

    outlet_candidates = outlets_mod.candidate_block(
        subject_focus, exclude=coverage.get("outlets") or set()
    )

    trends_section = generate_trends_section(
        subject_focus=subject_focus,
        digest_content=digest_content,
        outputs_dir=OUTPUTS_DIR,
        memory_dir=TOPIC_MEMORY_DIR,
        api_key=anthropic_api_key,
        outlet_candidates=outlet_candidates,
    )
    digest_content = digest_content.rstrip() + "\n\n---\n\n" + trends_section + "\n"

    digest_path.write_text(digest_content, encoding="utf-8")
    print(f"Digest saved: outputs/{digest_path.name}")

    # Everything the dashboard needs that cannot survive the trip through
    # markdown. Written beside the digest so a rebuild can score the run without
    # re-querying anything.
    write_run_sidecar(digest_path, coverage, summaries, selected_pmids)

    # ── Step 7: Rebuild dashboard data ───────────────────────────────────────
    print("\nRebuilding dashboard data...")
    rebuild_dashboard_data()

    print("\nDone ✓")


if __name__ == "__main__":
    main()
