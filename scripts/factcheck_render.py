"""Turn fact-check records into the report's markdown.

This is the file whose format drift caused the damage: the model wrote the report
as prose, the dashboard scraped verdicts back out with a regex pinned to
`### Study N:`, and when the model started writing `## Study N:` instead, 22 of
52 reports silently lost every verdict. Rendering from records means the heading
level is no longer the model's to choose.

The template matches what the model used to emit, so the parser reads new reports
and old ones the same way.
"""
from __future__ import annotations

VERDICT_SYMBOL = {
    "accurate": "✅ Accurate",
    "minor": "⚠️ Minor issues",
    "significant": "❌ Significant issues",
}
SEVERITIES = ("Minor", "Moderate", "Major")

STUDY_FIELDS = ("number", "pmid", "headline", "verdict", "notes", "issues")
ISSUE_FIELDS = ("label", "severity", "as_written", "abstract_says", "problem", "suggested_fix")


def _clean(value) -> str:
    return " ".join(str(value or "").split()).replace("|", "/")


def verdict_line(verdict: str) -> str:
    return VERDICT_SYMBOL.get(str(verdict or "").strip().lower(), VERDICT_SYMBOL["accurate"])


def render_issue(letter: str, issue: dict) -> str:
    severity = str(issue.get("severity", "Minor")).title()
    if severity not in SEVERITIES:
        severity = "Minor"
    return "\n".join([
        f"**Issue {letter}. {_clean(issue.get('label'))}** — Severity: {severity}",
        "",
        f'- **As written:** "{_clean(issue.get("as_written"))}"',
        f'- **Abstract says:** "{_clean(issue.get("abstract_says"))}"',
        f"- **Problem:** {_clean(issue.get('problem'))}",
        f'- **Suggested fix:** "{_clean(issue.get("suggested_fix"))}"',
        "",
    ])


def render_study(study: dict) -> str:
    issues = study.get("issues") or []
    if issues:
        body = "\n".join(
            render_issue(chr(ord("A") + i), issue) for i, issue in enumerate(issues)
        )
    else:
        body = "No factual errors found. Framing is consistent with the abstract.\n"
    return "\n".join([
        f"### Study {study.get('number')}: {_clean(study.get('headline'))}",
        f"**PMID:** {_clean(study.get('pmid'))} | "
        f"**Verdict:** {verdict_line(study.get('verdict'))}",
        "",
        body,
    ])


def severity_counts(studies: list[dict]) -> dict:
    counts = {s: 0 for s in SEVERITIES}
    for study in studies:
        for issue in study.get("issues") or []:
            severity = str(issue.get("severity", "Minor")).title()
            counts[severity if severity in counts else "Minor"] += 1
    return counts


def render_summary(studies: list[dict]) -> str:
    counts = severity_counts(studies)
    total = sum(counts.values())
    revision = sum(1 for s in studies
                   if str(s.get("verdict", "")).strip().lower() != "accurate")
    rows = "\n".join(
        f"| {s.get('number')} | {_clean(s.get('headline'))} | "
        f"{verdict_line(s.get('verdict'))} | {_clean(s.get('notes'))} |"
        for s in studies
    )
    return "\n".join([
        "## Issue Summary",
        "",
        "| Study # | Headline | Verdict | Notes |",
        "|---------|----------|---------|-------|",
        rows,
        "",
        f"**Total issues:** {total} ({counts['Minor']} Minor, "
        f"{counts['Moderate']} Moderate, {counts['Major']} Major)",
        f"**Entries requiring revision:** {revision}",
        f"**Entries cleared:** {len(studies) - revision}",
        "",
    ])


def render_report(studies: list[dict]) -> str:
    if not studies:
        return "_No studies were reviewed for this run._\n"
    return "\n".join(render_study(s) for s in studies) + "\n" + render_summary(studies)
