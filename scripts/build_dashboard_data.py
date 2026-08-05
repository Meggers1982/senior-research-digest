"""Parse every digest (and matching fact-check) in outputs/ into a single JSON
file the static dashboard (docs/) reads. Rebuilds from scratch each run so it
stays correct even if past output files are edited or renamed by hand."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs"
DASHBOARD_DATA_PATH = REPO_ROOT / "docs" / "data" / "digests.json"

HEADER_FIELD_RE = re.compile(r"\*\*([^*:]+):\*\*\s*([^\n|]+)")
STUDY_SPLIT_RE = re.compile(r"^### (\d+)\.\s*(.+)$", re.MULTILINE)
CITATION_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
FACT_CHECK_VERDICT_RE = re.compile(
    r"### Study \d+:.*?\n\*\*PMID:\*\*\s*(\d+)\s*\|\s*\*\*Verdict:\*\*\s*([^\n]+)"
)
FACT_CHECK_SUMMARY_RE = re.compile(
    r"\*\*Total issues:\*\*\s*([^\n]+)\n\*\*Entries requiring revision:\*\*\s*([^\n]+)\n\*\*Entries cleared:\*\*\s*([^\n]+)"
)


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
        studies.append(_parse_study_block(number, heading, block))
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

    fact_check_path = path.with_name(path.stem + " Fact Check.md")
    fact_check = _parse_fact_check(fact_check_path)

    run_date = header.get("Run date", "")
    topic = "" if is_broad else focus
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
        "fact_check": fact_check,
    }


def build() -> dict:
    runs = []
    for path in sorted(OUTPUTS_DIR.glob("*.md")):
        if path.name.endswith("Fact Check.md"):
            continue
        runs.append(_parse_digest_file(path))

    runs.sort(key=lambda r: (r["run_date"], r["filename"]), reverse=True)

    topics = sorted({r["topic"] for r in runs if r["topic"]})

    return {
        "generated_from": "outputs/*.md",
        "run_count": len(runs),
        "topics": topics,
        "runs": runs,
    }


def main() -> None:
    data = build()
    DASHBOARD_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(data['runs'])} runs to {DASHBOARD_DATA_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
