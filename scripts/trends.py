"""Compare a freshly generated digest against the most recent prior digest on the
same subject_focus, producing a short "Research Trends & Continuity" section."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic


SYSTEM_PROMPT = """\
You are a research editor comparing two research digests written weeks apart on the
same topic, each summarizing recent PubMed studies for an audience of older adults,
families, caregivers, and senior living professionals.

Compare the studies in the NEW digest against the studies in the PREVIOUS digest and
identify genuine connections only — do not force a link where none exists.

Organize findings under any of these headers that apply (omit any with nothing to report):

**Convergent findings** — new studies that replicate or reinforce previous conclusions.
**Advances** — new studies that extend, refine, or add meaningful nuance to previous findings.
**Counterpoints** — new studies that contradict, complicate, or weaken previous conclusions.
**New themes** — topics or angles not covered in the previous digest.

For each point, name the specific study headlines (and PMIDs) from both digests being
connected. Keep it tight — a handful of bullet points total, not a rewrite of either
digest. If there is genuinely no meaningful connection between the two digests, say so
plainly rather than inventing one.
"""


def _extract_field(text: str, field: str) -> str:
    """Extract a labelled field from a digest's header (mirrors fact_checker.py)."""
    match = re.search(rf"\*\*{re.escape(field)}:\*\*\s*([^\n|]+)", text)
    return match.group(1).strip() if match else ""


def _find_previous_digest(
    subject_focus: str, outputs_dir: Path
) -> Optional[tuple[Path, str]]:
    """Find the most recent digest in outputs_dir with a matching Focus field.

    Returns (path, file_content) for the best match, or None if no prior digest
    on this topic exists yet.
    """
    focus_key = subject_focus.strip().lower()
    best_path: Optional[Path] = None
    best_content: str = ""
    best_date: Optional[datetime] = None

    for path in outputs_dir.glob("*.md"):
        if path.name.endswith("Fact Check.md"):
            continue
        text = path.read_text(encoding="utf-8")
        focus_field = _extract_field(text, "Focus").strip().lower()
        is_match = focus_field.startswith("broad") if not focus_key else focus_field == focus_key
        if not is_match:
            continue

        run_date_str = _extract_field(text, "Run date")
        try:
            run_date = datetime.strptime(run_date_str, "%Y-%m-%d")
        except ValueError:
            continue

        if best_date is None or run_date > best_date:
            best_date = run_date
            best_path = path
            best_content = text

    if best_path is None:
        return None
    return best_path, best_content


def generate_trends_section(
    subject_focus: str,
    digest_content: str,
    outputs_dir: Path,
    api_key: str,
    model: str = "claude-opus-4-5",
) -> str:
    """Return a markdown "Research Trends & Continuity" section comparing this
    digest against the most recent prior digest on the same topic."""

    topic_label = subject_focus if subject_focus else "broad senior living"
    found = _find_previous_digest(subject_focus, outputs_dir)

    if found is None:
        return (
            "## Research Trends & Continuity\n\n"
            f"_No prior digest on **{topic_label}** was found to compare against — "
            "this is the first run on this topic._"
        )

    previous_path, previous_content = found
    previous_date = _extract_field(previous_content, "Run date") or previous_path.stem

    client = anthropic.Anthropic(api_key=api_key)
    user_message = (
        f"Topic: {topic_label}\n\n"
        f"{'=' * 60}\nNEW DIGEST (just written):\n\n{digest_content}\n\n"
        f"{'=' * 60}\nPREVIOUS DIGEST ({previous_date}):\n\n{previous_content}\n"
        f"{'=' * 60}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    body = response.content[0].text if response.content else ""
    if response.stop_reason == "max_tokens":
        print("  WARNING: trends section truncated — consider raising max_tokens.")

    return (
        "## Research Trends & Continuity\n"
        f"_Comparing against the {previous_date} digest on this topic._\n\n"
        + body.strip()
    )
