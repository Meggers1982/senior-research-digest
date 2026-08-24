"""Generate a senior living research digest using the Claude API."""

import json
import re
from datetime import datetime

import anthropic


SYSTEM_PROMPT = """\
You are an expert science journalist producing a curated research digest focused on
aging, senior living, and elder care. You will be given PubMed abstracts sourced
exclusively from peer-reviewed journals specializing in aging and gerontology.

Select the most newsworthy studies and write a structured entry for each one.

## Selection criteria
- Prioritize: human-subjects studies, RCTs, large cohorts, longitudinal data
- Favor studies with direct relevance to seniors, older adults, and the people
  who care for them (families, caregivers, senior living professionals)
- Include: findings with practical, day-to-day implications for the stated audiences
- Skip: editorials, letters, methodology-only papers, purely technical studies


## Spelling
Write in American English: "analyze", "behavior", "randomized", "center", "program",
"generalize". Many of these journals are British and their abstracts are not written
that way — convert as you write in your own voice. Never change spelling inside
something reproduced verbatim: journal titles (e.g. *Behaviour Research and Therapy*),
trial, instrument and cohort names, and direct quotations keep their original form.

## Entry format (use this exactly for every selected study)

### [Number]. [Compelling, plain-language headline]

**Journal:** *Name* | **Published:** Date
**PMID:** [ID] | **DOI:** [DOI or "Not available"]

**The study:** What researchers did, who participants were (N=, age range), key
finding in plain language. 2–4 sentences.

**Why it matters:** Practical significance for older adults, families, or senior care
professionals. 1–2 sentences.

**Story angles:**
- **To [PRIMARY_AUDIENCE]:** Direct, empowering angle using "you" language. What can
  they do, consider, ask about, or watch for? Do NOT imply clinical action based on
  observational data alone.
- **About [PRIMARY_AUDIENCE]:** Angle for [SECONDARY_AUDIENCE]. May address caregiving
  decisions, senior living policy, facility practice, or family guidance. Different
  framing from the "to" angle — not a rewording.

**Caveats:** Flag any that apply — small N (under 100 for quantitative studies),
single-center, observational design (cannot establish causation), industry funding
(name the funder), self-reported outcomes, population may not generalize, short
follow-up, no control group. Write "None significant" if none apply.

---

After all entries, write a citation table:

## Citation Reference

| # | PMID | Journal | Date | DOI |
|---|------|---------|------|-----|
[one row per entry]

Do not include your own top-level title or heading (e.g. a line starting with
"# Senior Living Research Digest") anywhere in your response — the output file
already has this title in its header. Start directly with the first entry.

Finally, append a JSON block (used internally — do not explain it):
```json
{"selected_pmids": ["pmid1", "pmid2"]}
```
"""

MAX_CONTINUATIONS = 3
CONTINUATION_PROMPT = (
    "Continue exactly where you left off. Do not repeat any content already "
    "written, and do not restart from the beginning."
)


def generate_digest(
    subject_focus: str,
    primary_audience: str,
    secondary_audience: str,
    abstracts: dict[str, str],
    journal_count: int,
    api_key: str,
    model: str = "claude-opus-4-5",
) -> tuple[str, list[str]]:
    """Generate a formatted senior living digest from PubMed abstracts.

    Returns:
        (full_digest_markdown, list_of_selected_pmids)
    """
    client = anthropic.Anthropic(api_key=api_key)

    run_date = datetime.now().strftime("%Y-%m-%d")
    month_year = datetime.now().strftime("%B %Y")

    # File header
    focus_label = subject_focus if subject_focus else "Broad (all senior living topics)"
    header_parts = [
        "# Senior Living Research Digest",
        f"**Run date:** {run_date} | **Coverage window:** Last 90 days",
        f"**Journals searched:** {journal_count} | **Articles screened:** {len(abstracts)}",
        f"**Focus:** {focus_label}",
        f"**Primary audience:** {primary_audience} | **Secondary audience:** {secondary_audience}",
    ]
    header = "\n".join(header_parts) + "\n\n---\n\n"

    if not abstracts:
        return header + "_No articles with usable abstracts were found for this run._", []

    abstracts_block = "\n\n".join(
        f"--- PMID {pmid} ---\n{text}" for pmid, text in abstracts.items()
    )

    system = (
        SYSTEM_PROMPT
        .replace("[PRIMARY_AUDIENCE]", primary_audience)
        .replace("[SECONDARY_AUDIENCE]", secondary_audience)
    )

    focus_line = f"**Subject focus:** {subject_focus}\n" if subject_focus else ""
    user_message = (
        f"Please write a senior living research digest for the {len(abstracts)} abstracts below.\n\n"
        f"**Primary audience:** {primary_audience}\n"
        f"**Secondary audience:** {secondary_audience}\n"
        + focus_line
        + "\nInclude all studies with strong story potential — do not cap the count.\n\n"
        f"{'=' * 60}\n"
        f"{abstracts_block}\n"
        f"{'=' * 60}"
    )

    # Cache the system prompt and the (large) initial abstracts message so that
    # continuation retries below re-read this prefix from cache instead of
    # reprocessing it at full price on every retry. Continuation turns are small
    # and left uncached to keep the request under the API's breakpoint limit.
    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": user_message, "cache_control": {"type": "ephemeral"}}],
        }
    ]
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=system_blocks,
        messages=messages,
    )
    chunk = response.content[0].text if response.content else ""
    body = chunk

    continuations = 0
    while response.stop_reason == "max_tokens" and continuations < MAX_CONTINUATIONS:
        # Echo back only THIS turn's partial text as the assistant message —
        # not the full accumulated body — so the conversation history mirrors
        # what actually happened turn-by-turn and doesn't duplicate content.
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": CONTINUATION_PROMPT})
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system_blocks,
            messages=messages,
        )
        chunk = response.content[0].text if response.content else ""
        body += chunk
        continuations += 1

    if response.stop_reason == "max_tokens":
        print(
            "  WARNING: digest response still truncated after "
            f"{MAX_CONTINUATIONS} continuation(s) — output may be incomplete."
        )

    # Extract selected PMIDs from the trailing JSON block (search the full
    # accumulated text, not just the last continuation chunk)
    selected_pmids = list(abstracts.keys())
    json_match = re.search(r"```json\s*(\{[^`]+\})\s*```", body, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            selected_pmids = data.get("selected_pmids", selected_pmids)
        except json.JSONDecodeError:
            pass
        body = body[: json_match.start()].rstrip()

    # Strip a leading H1 title line if the model included its own (belt and
    # suspenders alongside the system prompt instruction not to) — the file
    # header above already carries this title.
    stripped = body.lstrip("\n")
    first_line_end = stripped.find("\n")
    first_line = stripped if first_line_end == -1 else stripped[:first_line_end]
    if re.match(r"^#\s+.*Senior Living Research Digest", first_line.strip()):
        rest = "" if first_line_end == -1 else stripped[first_line_end + 1 :]
        rest = rest.lstrip("\n")
        body = rest

    return header + body, selected_pmids
