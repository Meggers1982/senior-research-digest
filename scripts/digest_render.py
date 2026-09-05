"""Turn study records into the digest's markdown.

The digest used to be markdown the model wrote, which `build_dashboard_data`
then regex-scraped back into fields. That coupling is what hid half the archive's
fact-check verdicts for months: the model changed one heading level and nothing
noticed. The model now returns records and this module renders them, so the
markdown is generated to a fixed template rather than parsed out of prose.

The template is byte-compatible with what the model used to produce, so the
existing parser keeps working on new files and old ones alike — and
`tests/test_digest_render.py` proves it by rendering records, parsing them back,
and comparing.
"""
from __future__ import annotations

STUDY_FIELDS = (
    "headline", "journal", "published", "pmid", "doi",
    "the_study", "why_it_matters",
    "story_angle_primary", "story_angle_secondary", "caveats",
)


def _clean(value) -> str:
    """One line, no stray pipes — a pipe would break the citation table row."""
    return " ".join(str(value or "").split()).replace("|", "/")


def render_study(number: int, study: dict, primary: str, secondary: str) -> str:
    doi = _clean(study.get("doi")) or "Not available"
    return "\n".join([
        f"### {number}. {_clean(study.get('headline'))}",
        "",
        f"**Journal:** *{_clean(study.get('journal'))}* | "
        f"**Published:** {_clean(study.get('published'))}",
        f"**PMID:** {_clean(study.get('pmid'))} | **DOI:** {doi}",
        "",
        f"**The study:** {_clean(study.get('the_study'))}",
        "",
        f"**Why it matters:** {_clean(study.get('why_it_matters'))}",
        "",
        "**Story angles:**",
        f"- **To {primary}:** {_clean(study.get('story_angle_primary'))}",
        f"- **About {primary}:** {_clean(study.get('story_angle_secondary'))}",
        "",
        f"**Caveats:** {_clean(study.get('caveats')) or 'None significant'}",
        "",
        "---",
        "",
    ])


def render_citation_table(studies: list[dict]) -> str:
    rows = "\n".join(
        f"| {i} | {_clean(s.get('pmid'))} | {_clean(s.get('journal'))} | "
        f"{_clean(s.get('published'))} | {_clean(s.get('doi')) or 'Not available'} |"
        for i, s in enumerate(studies, start=1)
    )
    return "\n".join([
        "## Citation Reference",
        "",
        "| # | PMID | Journal | Date | DOI |",
        "|---|------|---------|------|-----|",
        rows,
        "",
    ])


def render_digest(studies: list[dict], primary: str, secondary: str) -> str:
    """The body of the digest: every entry, then the citation table."""
    entries = "".join(
        render_study(i, s, primary, secondary)
        for i, s in enumerate(studies, start=1)
    )
    if not studies:
        return "_No studies were selected for this run._\n"
    return entries + render_citation_table(studies)
