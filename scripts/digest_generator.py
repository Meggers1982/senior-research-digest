"""Generate a senior living research digest using the Claude API."""

from datetime import datetime

import anthropic

import digest_render
import llm


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

## What to return

Return one record per selected study. Field by field:

- `headline`: compelling, plain-language, not the paper's own title
- `journal`, `published`, `pmid`, `doi`: exactly as given in the abstract block.
  Use "Not available" for a missing DOI. Never invent or alter a PMID.
- `the_study`: what researchers did, who participants were (N=, age range), and
  the key finding in plain language. 2-4 sentences.
- `why_it_matters`: practical significance for older adults, families, or senior
  care professionals. 1-2 sentences.
- `story_angle_primary`: a direct, empowering angle for [PRIMARY_AUDIENCE] in
  "you" language — what to do, consider, ask about or watch for. Do NOT imply
  clinical action on observational data alone.
- `story_angle_secondary`: an angle for [SECONDARY_AUDIENCE]. A different
  framing, not the primary angle addressed to a different reader. Where a study
  supports no real question for them, say so briefly rather than padding.
- `caveats`: flag any that apply — small N (under 100 for quantitative studies),
  single-center, observational design (cannot establish causation), industry
  funding (name the funder), self-reported outcomes, population may not
  generalize, short follow-up, no control group. "None significant" if none do.

Select only the studies worth writing up. Returning fewer records than there are
abstracts is expected and correct; a weak study left out is better than a weak
entry written up.
"""

# One record per study, so a malformed answer is an API-level error rather than a
# regex that quietly matches nothing.
STUDY_SCHEMA = {
    "type": "object",
    "properties": {
        "studies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    field: {"type": "string"} for field in digest_render.STUDY_FIELDS
                },
                "required": list(digest_render.STUDY_FIELDS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["studies"],
    "additionalProperties": False,
}

# A JSON response cannot be stitched back together across turns the way prose
# could, so the input is batched to keep every answer inside one turn instead.
ABSTRACTS_PER_CALL = 12


def generate_digest(
    subject_focus: str,
    primary_audience: str,
    secondary_audience: str,
    abstracts: dict[str, str],
    journal_count: int,
    api_key: str,
    model: str = llm.MODEL,
) -> tuple[str, list[str], list[dict]]:
    """Generate a senior living digest from PubMed abstracts.

    Returns:
        (full_digest_markdown, selected_pmids, study_records)

    The markdown is rendered here from the records, not written by the model, so
    the format the dashboard parses cannot drift out from under it.
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
        return header + "_No articles with usable abstracts were found for this run._", [], []

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
    system_blocks = [llm.cached(system)]

    records = []
    pmids = list(abstracts)
    batches = [pmids[i:i + ABSTRACTS_PER_CALL]
               for i in range(0, len(pmids), ABSTRACTS_PER_CALL)]
    for index, batch in enumerate(batches, start=1):
        block = "\n\n".join(f"--- PMID {pmid} ---\n{abstracts[pmid]}" for pmid in batch)
        message = (
            f"Batch {index} of {len(batches)}. Write up the newsworthy studies among "
            f"the {len(batch)} abstracts below.\n\n"
            f"**Primary audience:** {primary_audience}\n"
            f"**Secondary audience:** {secondary_audience}\n"
            + focus_line
            + f"\n{'=' * 60}\n{block}\n{'=' * 60}"
        )
        try:
            parsed = llm.complete_json(
                client,
                system=system_blocks,
                messages=[{"role": "user", "content": message}],
                schema=STUDY_SCHEMA,
                label=f"digest batch {index}",
                model=model,
            )
        except llm.ModelDeclined as exc:
            print(f"  WARNING: batch {index} declined ({exc}); its studies are omitted.")
            continue
        records.extend(parsed.get("studies") or [])

    # A PMID the model invented is worse than a study left out, so records are
    # kept only where the PMID is one that was actually sent.
    known = set(abstracts)
    kept, dropped = [], []
    for record in records:
        pmid = str(record.get("pmid", "")).strip()
        (kept if pmid in known else dropped).append(record)
    if dropped:
        print(f"  WARNING: dropped {len(dropped)} record(s) citing a PMID that was "
              "not in this run.")

    body = digest_render.render_digest(kept, primary_audience, secondary_audience)
    return header + body, [r["pmid"] for r in kept], kept
