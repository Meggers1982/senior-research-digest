"""Compare a freshly generated digest against the most recent prior digest on the
same subject_focus, surface any cross-study pattern within the new digest that might
justify a standalone feature pitch, and maintain a persistent per-topic memory file
so both of the above can draw on the topic's full history, not just the single most
recent digest."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

import llm


SYSTEM_PROMPT = """\
You are a research editor producing a short synthesis to run at the end of a senior
living research digest, for an audience of older adults, families, caregivers, and
senior living professionals.

You will be given the digest just written (NEW DIGEST), if one exists the most
recent digest on the same topic (PREVIOUS DIGEST), and a running cross-run summary
for this topic (TOPIC MEMORY, which may be empty if this is the first run). Write
exactly three visible sections plus one hidden block, using this structure and
headers verbatim:


## Spelling
Write in American English: "analyze", "behavior", "randomized", "center", "program",
"generalize". Many of these journals are British and their abstracts are not written
that way — convert as you write in your own voice. Never change spelling inside
something reproduced verbatim: journal titles (e.g. *Behaviour Research and Therapy*),
trial, instrument and cohort names, and direct quotations keep their original form.

## Research Trends & Continuity

Compare the studies in the NEW digest against the studies in the PREVIOUS digest.
Identify genuine connections only — do not force a link where none exists. Organize
under any of these that apply (omit any with nothing to report): **Convergent
findings**, **Advances**, **Counterpoints**, **New themes**. Name the specific study
headlines and PMIDs from both digests for each point. If there is no previous digest,
write only: "_No prior digest on this topic to compare against yet — this is the
first run._"

## Bigger Picture: Feature Pitch

Independent of the comparison above, look across ONLY the studies in the NEW digest
as a batch. Do several of them, taken together, point to a broader trend, an emerging
or underreported issue, or a storyline that would justify a standalone feature —
something bigger than any single study's own "story angles"?

If yes, write:
**The pattern:** what the cross-study thread is, naming the specific study headlines
and PMIDs from the NEW digest that support it (2-3 sentences).
**Why pitch this now:** why this is timely or newsworthy as a larger feature, not just
as individual items (1-2 sentences).
**Angle:** how a longer feature piece could be framed, and for which audience
(1-2 sentences).
**Potential headlines:** 3 working headlines for the FEATURE itself, not for any
single study inside it — each its own bullet. Vary them rather than writing one
headline three ways: one plain and concrete about what the evidence shows, one
that leads with the counterintuitive turn, one that names what is at stake for
the reader. Each should be specific enough to tell this feature apart from a
generic piece on the topic. Avoid the colon-plus-subtitle formula unless it
genuinely earns its place, avoid "Here's what X means for Y" constructions, and
do not promise anything the studies behind this pitch would not support.
Register: plain language an older adult or a family caregiver would read
without a medical dictionary. Warm but not patronizing, and never alarmist.
**Potential outlets:** 3-4 real, currently active publications this specific pitch
could go to, each its own bullet with a short reason tied to THIS angle (not a
generic "they cover health topics"). Mix consumer press aimed at older adults or
caregivers with senior-care trade press where relevant. Prefer the candidates
listed under CANDIDATE OUTLETS below — they come from the AgingWire publisher
prospecting database, and the note after each is why that outlet was scored a
good target. You are not limited to that list; name a better-fitting publication
if you know one. Never name an outlet listed as already reporting these studies,
and never name one that wouldn't plausibly run this particular angle.

If the studies in this batch are disconnected single findings with no genuine
cross-study pattern, write only: "_No cross-study feature angle identified in this
batch._" Do not manufacture a pattern that isn't really there.

## Story Ideas by Study

Independent of both sections above, go through the studies in the NEW digest one
at a time — not as a batch. For every study that has a genuinely pitchable angle
on its own, give it one line: a specific angle sharp enough for a writer to act
on, plus what kind of outlet or section it fits (for example: a caregiver-advice
column, a senior-living trade brief, a consumer health explainer, a local-news
health segment). Same audience as above: older adults, families, caregivers, and
senior living professionals — match that register.

Cover every study in the NEW digest worth pitching, not a curated handful — the
point of this section is that nothing pitchable gets missed. Skip only a study
that is genuinely thin or routine, with nothing to say beyond its own headline.

Name each study by its headline and PMID, the same way the Research Trends &
Continuity section above cites specific study headlines and PMIDs. Format as one
bullet per study:

- **[Study headline] (PMID [number]):** [the angle], for [outlet type/section].

If nothing in the NEW digest has an individual pitch worth making, write only:
"_No individual study pitches identified in this digest._" Do not force an angle
onto a study that doesn't have one.

Finally, revise TOPIC MEMORY in light of the NEW digest and append it as a fenced
block (used internally — do not explain it, and do not repeat its contents in either
visible section above):

```topic_memory
## Established findings
- [well-supported conclusions that have recurred across multiple runs on this topic,
  with representative PMIDs/dates]

## Emerging threads
- [newer patterns not yet fully established, worth watching in future runs]

## Feature ideas already pitched
- [short log of past "Bigger Picture" pitches, so future runs don't re-pitch the
  same angle]
```

Keep TOPIC MEMORY tight — a dozen bullets total across all three subsections, not a
running log of every study ever covered. Merge, prune, or drop items that are stale
or no longer relevant rather than letting the list grow indefinitely. If TOPIC MEMORY
was empty, base it only on the NEW digest.
"""


def _extract_field(text: str, field: str) -> str:
    """Extract a labeled field from a digest's header (mirrors fact_checker.py)."""
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


def _slugify(subject_focus: str) -> str:
    if not subject_focus:
        return "broad"
    return re.sub(r"[^a-z0-9]+", "-", subject_focus.strip().lower()).strip("-")


def _topic_memory_path(subject_focus: str, memory_dir: Path) -> Path:
    return memory_dir / f"{_slugify(subject_focus)}.md"


CONTINUATION_PROMPT = (
    "Continue exactly where you left off. Do not repeat any content already "
    "written, and do not restart from the beginning."
)


def generate_trends_section(
    subject_focus: str,
    digest_content: str,
    outputs_dir: Path,
    memory_dir: Path,
    api_key: str,
    model: str = llm.MODEL,
    outlet_candidates: str = "",
) -> str:
    """Return markdown covering (1) how this digest's studies compare to the most
    recent prior digest on the same topic, and (2) whether this digest's own studies,
    taken together, suggest a bigger cross-study trend worth pitching as a feature.

    As a side effect, revises and persists a per-topic memory file in memory_dir so
    future runs on this topic can draw on the full history, not just the single most
    recent digest."""

    topic_label = subject_focus if subject_focus else "broad senior living"
    found = _find_previous_digest(subject_focus, outputs_dir)
    previous_block = (
        found[1] if found is not None else "(none — this is the first digest on this topic)"
    )

    memory_path = _topic_memory_path(subject_focus, memory_dir)
    existing_memory = (
        memory_path.read_text(encoding="utf-8")
        if memory_path.exists()
        else "(none yet — this is the first run on this topic)"
    )

    client = anthropic.Anthropic(api_key=api_key)
    candidate_block = (
        f"{'=' * 60}\nCANDIDATE OUTLETS:\n\n{outlet_candidates}\n\n"
        if outlet_candidates else ""
    )
    user_message = (
        f"Topic: {topic_label}\n\n"
        f"{candidate_block}"
        f"{'=' * 60}\nNEW DIGEST (just written):\n\n{digest_content}\n\n"
        f"{'=' * 60}\nPREVIOUS DIGEST:\n\n{previous_block}\n\n"
        f"{'=' * 60}\nTOPIC MEMORY:\n\n{existing_memory}\n"
        f"{'=' * 60}"
    )

    # This call sends the largest payload in the pipeline -- a whole new digest,
    # a whole previous one and the topic memory -- and was the only one with
    # neither prompt caching nor a continuation retry. It now has both.
    body = llm.complete_prose(
        client,
        system=[llm.cached(SYSTEM_PROMPT)],
        messages=[{"role": "user", "content": [llm.cached(user_message)]}],
        continuation_prompt=CONTINUATION_PROMPT,
        label="trends section",
        model=model,
    )

    # Extract and persist the trailing topic-memory block; strip it from the
    # visible text returned for the digest. If the block is missing (e.g. this
    # response got truncated before reaching it), leave the existing memory file
    # untouched rather than overwriting it with a partial/garbled version.
    memory_match = re.search(r"```topic_memory\s*(.*?)```", body, re.DOTALL)
    if memory_match:
        memory_dir.mkdir(parents=True, exist_ok=True)
        updated_memory = (
            f"# Topic Memory: {topic_label}\n"
            f"_Last updated: {datetime.now().strftime('%Y-%m-%d')}_\n\n"
            + memory_match.group(1).strip()
            + "\n"
        )
        memory_path.write_text(updated_memory, encoding="utf-8")
        body = body[: memory_match.start()].rstrip()

    return body.strip()
