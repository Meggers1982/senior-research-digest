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
    trends_section = generate_trends_section(
        subject_focus=subject_focus,
        digest_content=digest_content,
        outputs_dir=OUTPUTS_DIR,
        memory_dir=TOPIC_MEMORY_DIR,
        api_key=anthropic_api_key,
    )
    digest_content = digest_content.rstrip() + "\n\n---\n\n" + trends_section + "\n"

    digest_path.write_text(digest_content, encoding="utf-8")
    print(f"Digest saved: outputs/{digest_path.name}")

    # ── Step 7: Rebuild dashboard data ───────────────────────────────────────
    print("\nRebuilding dashboard data...")
    rebuild_dashboard_data()

    print("\nDone ✓")


if __name__ == "__main__":
    main()
