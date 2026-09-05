"""Parse every digest (and matching fact-check) in outputs/ into the JSON the
static dashboard (docs/) reads. Rebuilds from scratch each run so it stays
correct even if past output files are edited or renamed by hand.

Output is split so the dashboard's first load stays flat as runs accumulate:
`index.json` holds only what the sidebar and the search box need (roughly 5%
of the total), and each run's full body goes to `runs/<id>.json`, fetched on
demand when that run is opened."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs"
DASHBOARD_DATA_DIR = REPO_ROOT / "docs" / "data"
DASHBOARD_INDEX_PATH = DASHBOARD_DATA_DIR / "index.json"
DASHBOARD_RUNS_DIR = DASHBOARD_DATA_DIR / "runs"
TOPIC_DEMAND_SRC = OUTPUTS_DIR / "topic-demand.json"
TOPIC_DEMAND_OUT = DASHBOARD_DATA_DIR / "topic-demand.json"
LEGACY_DATA_PATH = DASHBOARD_DATA_DIR / "digests.json"

HEADER_FIELD_RE = re.compile(r"\*\*([^*:]+):\*\*\s*([^\n|]+)")
STUDY_SPLIT_RE = re.compile(r"^### (\d+)\.\s*(.+)$", re.MULTILINE)
CITATION_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
FACT_CHECK_VERDICT_RE = re.compile(
    r"^#{2,4}\s*Study\s*\d+:[^\n]*\n+\*\*PMID:\*\*\s*(\d+)\s*\|\s*"
    r"\*\*Verdict:\*\*\s*([^\n]+)",
    re.MULTILINE,
)
FACT_CHECK_SUMMARY_RE = re.compile(
    r"\*\*Total issues:\*\*\s*([^\n]+)\n\*\*Entries requiring revision:\*\*\s*([^\n]+)\n\*\*Entries cleared:\*\*\s*([^\n]+)"
)


# outputs/ is not exclusively digests -- topic_demand.py writes its report there
# too, and the "*.md" glob was turning it into a dateless, studyless ghost run.
DIGEST_TITLE_PREFIX = "Senior Living Research Digest"


def is_digest(path: Path) -> bool:
    """A digest is identified by its own header, not by its filename, so a
    renamed file still parses and a new report dropped into outputs/ does not
    become a run."""
    if path.name.endswith("Fact Check.md"):
        return False
    try:
        head = path.read_text(encoding="utf-8")[:2000]
    except OSError:
        return False
    return DIGEST_TITLE_PREFIX.lower() in head.lower() and "**Run date:**" in head


# The rotation was reworded from "fall prevention" to "falls" partway through the
# archive, which gave the topic filter two entries covering the same beat.
TOPIC_ALIASES = {"fall prevention": "falls"}


def normalize_topic(topic: str) -> str:
    return TOPIC_ALIASES.get(topic.strip().lower(), topic.strip())


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "untitled"


def _header_fields(text: str) -> dict:
    fields = {}
    for label, value in HEADER_FIELD_RE.findall(text):
        fields[label.strip()] = value.strip()
    return fields


def _parse_study_block(number: str, heading: str, body: str) -> dict:
    fields = _header_fields(body)

    def _section(name: str) -> str:
        match = re.search(
            rf"\*\*{re.escape(name)}:\*\*\s*(.+?)(?=\n\*\*[A-Za-z][^*]*:\*\*|\Z)",
            body,
            re.DOTALL,
        )
        if not match:
            return ""
        value = match.group(1).strip()
        # Drop a trailing "---" divider (and anything after it) that spills into
        # the last field when no bold label follows before the next study/heading.
        value = re.split(r"\n\s*-{3,}\s*", value)[0]
        return value.strip()

    story_angles_block = _section("Story angles")
    to_match = re.search(
        r"-\s*\*\*To [^:*]+:\*\*\s*(.+?)(?=\n-\s*\*\*About|\Z)", story_angles_block, re.DOTALL
    )
    about_match = re.search(r"-\s*\*\*About [^:*]+:\*\*\s*(.+)", story_angles_block, re.DOTALL)

    return {
        "number": int(number),
        "title": heading.strip(),
        "journal": fields.get("Journal", "").strip("* "),
        "published": fields.get("Published", ""),
        "pmid": fields.get("PMID", ""),
        "doi": fields.get("DOI", ""),
        "the_study": _section("The study"),
        "why_it_matters": _section("Why it matters"),
        "story_angle_primary": to_match.group(1).strip() if to_match else "",
        "story_angle_secondary": about_match.group(1).strip() if about_match else "",
        "caveats": _section("Caveats"),
    }


def _parse_studies(body: str) -> list[dict]:
    matches = list(STUDY_SPLIT_RE.finditer(body))
    studies = []
    for i, match in enumerate(matches):
        number, heading = match.group(1), match.group(2)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end]
        # Trim trailing citation table / trends / feature-pitch sections that
        # follow the last study entry.
        block = re.split(r"\n## ", block)[0]
        study = _parse_study_block(number, heading, block)
        # Five June/July digests end partway through their final entry -- they
        # predate the continuation retry that fixed max_tokens truncation. The
        # tail block is a heading, sometimes a PMID, and no body. That renders as
        # an empty card, so drop it rather than publish one. A truncated entry
        # that still has a body is kept; only "Why it matters" is missing and the
        # card reads fine without it.
        if not study["the_study"]:
            continue
        studies.append(study)
    return studies


def _parse_named_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    return match.group(1).strip() if match else ""


def _parse_fact_check(path: Path) -> dict | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    header = _header_fields(text)
    verdicts = {
        pmid: verdict.strip() for pmid, verdict in FACT_CHECK_VERDICT_RE.findall(text)
    }
    summary_match = FACT_CHECK_SUMMARY_RE.search(text)
    summary = None
    if summary_match:
        summary = {
            "total_issues": summary_match.group(1).strip(),
            "entries_requiring_revision": summary_match.group(2).strip(),
            "entries_cleared": summary_match.group(3).strip(),
        }
    return {
        "checked": header.get("Checked", ""),
        "studies_reviewed": header.get("Studies reviewed", ""),
        "verdicts_by_pmid": verdicts,
        "summary": summary,
        "raw": text,
    }


def _parse_digest_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    header = _header_fields(text)
    body = text.split("---", 1)[1] if "---" in text else text

    focus = header.get("Focus", "")
    is_broad = focus.strip().lower().startswith("broad")

    studies = _parse_studies(body)
    citation_rows = CITATION_ROW_RE.findall(text)

    trends_raw = _parse_named_section(text, "Research Trends & Continuity")
    feature_pitch_raw = _parse_named_section(text, "Bigger Picture: Feature Pitch")
    pitch_ideas_raw = _parse_named_section(text, "Story Ideas by Study")

    fact_check_path = path.with_name(path.stem + " Fact Check.md")
    fact_check = _parse_fact_check(fact_check_path)

    run_date = header.get("Run date", "")
    topic = "" if is_broad else normalize_topic(focus)
    run_id = f"{path.stem}"

    return {
        "id": _slugify(run_id),
        "filename": path.name,
        "title": path.stem,
        "run_date": run_date,
        "coverage_window": header.get("Coverage window", ""),
        "journals_searched": header.get("Journals searched", ""),
        "articles_screened": header.get("Articles screened", ""),
        "focus": focus,
        "topic": topic,
        "is_broad": is_broad,
        "primary_audience": header.get("Primary audience", ""),
        "secondary_audience": header.get("Secondary audience", ""),
        "study_count": len(studies),
        "studies": studies,
        "citation_table": [
            {"pmid": pmid, "journal": journal, "date": date, "doi": doi}
            for pmid, journal, date, doi in citation_rows
        ],
        "trends_raw": trends_raw,
        "feature_pitch_raw": feature_pitch_raw,
        "pitch_ideas_raw": pitch_ideas_raw,
        "fact_check": fact_check,
    }


def _search_blob(run: dict) -> str:
    """Everything the search box matches on, flattened at build time so the
    index doesn't have to carry the full study objects."""
    parts = [run.get("title", ""), run.get("focus", ""), run.get("topic", "")]
    for study in run.get("studies", []):
        parts.extend([study.get("title", ""), study.get("pmid", ""), study.get("journal", "")])
    return " ".join(p for p in parts if p).lower()


def _index_entry(run: dict) -> dict:
    fact_check = run.get("fact_check") or {}
    summary = fact_check.get("summary") or {}
    return {
        "id": run["id"],
        "title": run.get("title", ""),
        "topic": run.get("topic", ""),
        "run_date": run.get("run_date", ""),
        "study_count": run.get("study_count", 0),
        "total_issues": summary.get("total_issues", ""),
        "search": _search_blob(run),
    }


def build() -> list:
    runs = []
    for path in sorted(OUTPUTS_DIR.glob("*.md")):
        if not is_digest(path):
            continue
        runs.append(_parse_digest_file(path))

    runs.sort(key=lambda r: (r["run_date"], r["filename"]), reverse=True)

    # Two outputs can slugify to the same id; keep them addressable as separate
    # files rather than letting the later one overwrite the earlier.
    seen = {}
    for run in runs:
        base = run["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            run["id"] = f"{base}-{seen[base]}"

    return runs


def copy_topic_demand() -> bool:
    """topic_demand.py writes a real weekly report that nothing consumed --
    it was only visible as an empty ghost run. Publish it as its own document,
    normalising topic names so it lines up with the rotation the dashboard shows.
    """
    try:
        data = json.loads(TOPIC_DEMAND_SRC.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    data["rotation"] = {
        normalize_topic(topic): value
        for topic, value in (data.get("rotation") or {}).items()
    }
    data["no_signal"] = sorted({normalize_topic(t) for t in (data.get("no_signal") or [])})
    TOPIC_DEMAND_OUT.parent.mkdir(parents=True, exist_ok=True)
    TOPIC_DEMAND_OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def main() -> None:
    runs = build()

    DASHBOARD_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    written = set()
    for run in runs:
        path = DASHBOARD_RUNS_DIR / f"{run['id']}.json"
        path.write_text(json.dumps(run, indent=2), encoding="utf-8")
        written.add(path.name)

    # Drop run files whose source markdown was renamed or deleted.
    stale = [p for p in DASHBOARD_RUNS_DIR.glob("*.json") if p.name not in written]
    for path in stale:
        path.unlink()

    index = {
        "generated_from": "outputs/*.md",
        "run_count": len(runs),
        "topics": sorted({r["topic"] for r in runs if r["topic"]}),
        "runs": [_index_entry(r) for r in runs],
    }
    index["has_topic_demand"] = copy_topic_demand()
    DASHBOARD_INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Superseded by index.json + runs/; removing it stops the old whole-history
    # blob from being re-committed on every daily run.
    if LEGACY_DATA_PATH.exists():
        LEGACY_DATA_PATH.unlink()

    index_kb = DASHBOARD_INDEX_PATH.stat().st_size / 1024
    print(
        f"Wrote {len(runs)} runs to {DASHBOARD_RUNS_DIR.relative_to(REPO_ROOT)}/ "
        f"and {DASHBOARD_INDEX_PATH.relative_to(REPO_ROOT)} ({index_kb:.0f} KB)"
        + (f"; pruned {len(stale)} stale run file(s)" if stale else "")
    )


if __name__ == "__main__":
    main()
