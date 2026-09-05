"""Fact-check a research digest against original PubMed abstracts using Claude."""

import re
from datetime import datetime
from typing import Optional

import anthropic

import factcheck_render
import llm

from pubmed import fetch_abstract


SYSTEM_PROMPT = """\
You are a rigorous science editor fact-checking a medical research digest against
the original published abstracts. For each study, compare the digest text against
the provided abstract and check four areas:

1. **Study facts** — sample size (N), population, study design, institution/country,
   follow-up period, journal name, and publication date
2. **Statistical findings** — numbers, percentages, effect sizes, direction of effect,
   outcome variable correctly named, significance accurately represented
3. **Framing** — no causal language ("causes", "prevents") for observational findings;
   no overgeneralization beyond the study population; "Why it matters" doesn't leap
   beyond what the data support
4. **Story angles** — no clinical recommendations from preliminary or observational data;
   no hype language ("breakthrough", "could reverse", "eliminates", "proven to prevent");
   audience language appropriate for the stated primary/secondary audiences


## Spelling
Write your own commentary in American English ("analyze", "behavior", "randomized",
"center"). This does NOT apply to anything you quote: **As written:** and
**Abstract says:** must reproduce the digest and the abstract character for
character, British spellings included, and a spelling difference is never itself
an issue worth flagging. Journal titles and instrument names also keep their
original spelling.

## What to return

Return one record per study in the digest, in the digest's own order:

- `number`: the study's number in the digest
- `pmid`: its PMID, copied exactly
- `headline`: its headline, copied from the digest
- `verdict`: one of "accurate", "minor", "significant"
- `notes`: a short note for the summary table, or "" when there is nothing to say
- `issues`: one record per problem found, empty when there are none. Each carries
  a short `label`, a `severity` of Minor / Moderate / Major, the `as_written`
  quote from the digest, what the `abstract_says`, the `problem` in plain
  language, and a `suggested_fix`.

## Severity
- **Minor** — Small inaccuracy that doesn't change meaning (slightly wrong N, rounded stat)
- **Moderate** — Overstates or misrepresents a finding (causal language for observational data,
  wrong outcome variable, missing a key limitation)
- **Major** — Factually wrong, reverses direction of finding, or could cause a reader
  to act on incorrect information

## Scope
Check against the abstract only — not full-text or supplementary data.
Claims that cannot be verified from the abstract: flag as "Unverifiable from abstract only."
If the digest already flags a limitation in Caveats, don't re-flag it unless the body
text contradicts the caveat.
Industry funding in the abstract that the digest omitted from Caveats: flag as Moderate.

The report's headings, issue lettering and summary table are generated from these
records — do not write them yourself.
"""

# One record per study. The report is rendered from these, so the heading level
# the verdict regex depends on is no longer the model's to choose.
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "studies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "pmid": {"type": "string"},
                    "headline": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["accurate", "minor", "significant"]},
                    "notes": {"type": "string"},
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                field: {"type": "string"}
                                for field in factcheck_render.ISSUE_FIELDS
                            },
                            "required": list(factcheck_render.ISSUE_FIELDS),
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["number", "pmid", "headline", "verdict", "notes", "issues"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["studies"],
    "additionalProperties": False,
}

# As in digest_generator: a JSON answer cannot be stitched across turns, so the
# input is batched to keep each answer inside one.
STUDIES_PER_CALL = 10

# Cache the (static) system prompt; the digest is repeated in every batch and is
# marked cacheable at the call site.
SYSTEM_PROMPT_BLOCKS = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _extract_header_field(digest: str, field: str) -> str:
    """Extract a labeled field from the digest header."""
    match = re.search(rf"\*\*{re.escape(field)}:\*\*\s*([^\n|]+)", digest)
    return match.group(1).strip() if match else ""


def run_fact_check(
    digest_content: str,
    selected_pmids: list[str],
    ncbi_api_key: Optional[str],
    anthropic_api_key: str,
    model: str = llm.MODEL,
    subject_focus: str = "",
) -> tuple[str, list[dict]]:
    """Fact-check a digest against the original abstracts.

    Returns (report_markdown, study_records). The markdown is rendered from the
    records rather than written by the model, so the verdict format the dashboard
    reads cannot drift.
    """

    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Parse header fields from the digest
    primary_audience = _extract_header_field(digest_content, "Primary audience")
    secondary_audience = _extract_header_field(digest_content, "Secondary audience")
    category_line = (
        f"Senior Living Research Digest{' — ' + subject_focus.title() if subject_focus else ''}"
    )

    run_date = datetime.now().strftime("%Y-%m-%d")
    month_year = datetime.now().strftime("%B %Y")

    def header(reviewed: int) -> str:
        # The header used to report the number of abstracts sent, not the number
        # of studies actually reviewed -- 13 archived reports say "40" against
        # ~20 verdicts. It counts what was really checked.
        return (
            f"# Fact-Check Report: {category_line} — {month_year}\n"
            f"**Checked:** {run_date} | **Studies reviewed:** {reviewed}\n"
            f"**Primary audience:** {primary_audience} | "
            f"**Secondary audience:** {secondary_audience}\n\n"
            "---\n\n"
        )

    # A run can legitimately select no studies: the digest prompt says returning
    # fewer records than abstracts is expected and correct. Without this guard
    # the batch list below evaluates to [[]] and still spends one full call
    # asking the model to fact-check nothing.
    if not selected_pmids:
        print("  No studies selected; skipping fact check.")
        return header(0) + factcheck_render.render_report([]), []

    # Re-fetch abstracts for every selected PMID
    print(f"  Fetching {len(selected_pmids)} abstracts for fact-check...")
    abstracts: dict[str, str] = {}
    for pmid in selected_pmids:
        try:
            text = fetch_abstract(pmid, ncbi_api_key)
            abstracts[pmid] = text if text.strip() else "ABSTRACT UNAVAILABLE FROM PUBMED"
        except Exception as e:
            print(f"  Warning: Could not fetch PMID {pmid}: {e}")
            abstracts[pmid] = "ABSTRACT UNAVAILABLE FROM PUBMED"

    # Batched so each answer fits in one turn; a truncated JSON report cannot be
    # repaired by continuing it. Studies are grouped in digest order.
    pmid_list = list(abstracts)
    batches = [pmid_list[i:i + STUDIES_PER_CALL]
               for i in range(0, len(pmid_list), STUDIES_PER_CALL)] or [[]]

    records = []
    for index, batch in enumerate(batches, start=1):
        block = "\n\n".join(f"--- PMID {pmid} ---\n{abstracts[pmid]}" for pmid in batch)
        user_message = (
            f"Fact-check the digest below against the original abstracts. "
            f"Batch {index} of {len(batches)}: check only the studies whose PMIDs "
            f"appear in the abstracts section.\n\n"
            f"**Primary audience:** {primary_audience}\n"
            f"**Secondary audience:** {secondary_audience}\n\n"
            f"{'=' * 60}\n"
            f"DIGEST TO CHECK:\n\n"
            f"{digest_content}\n\n"
            f"{'=' * 60}\n"
            f"ORIGINAL ABSTRACTS:\n\n"
            f"{block}\n"
            f"{'=' * 60}"
        )
        # The digest is repeated in every batch, so mark it cacheable.
        messages = [{"role": "user", "content": [llm.cached(user_message)]}]
        try:
            parsed = llm.complete_json(
                client,
                system=SYSTEM_PROMPT_BLOCKS,
                messages=messages,
                schema=REPORT_SCHEMA,
                label=f"fact-check batch {index}",
                model=model,
            )
        except llm.ModelDeclined as exc:
            print(f"  WARNING: fact-check batch {index} declined ({exc}); "
                  "its studies are reported as unchecked.")
            continue
        except ValueError as exc:
            # complete_json raises ValueError when the answer hit max_tokens
            # (a half-written JSON array cannot be stitched), and
            # json.JSONDecodeError -- itself a ValueError -- when the payload
            # will not parse. Either way this batch is unusable, but it is
            # only one batch: letting it propagate would take the whole run
            # down and lose the digest entirely.
            print(f"  WARNING: fact-check batch {index} returned unusable JSON "
                  f"({exc}); its studies are reported as unchecked.")
            continue
        records.extend(parsed.get("studies") or [])

    # Keep only verdicts for PMIDs actually in this run, and only one each.
    seen, kept = set(), []
    for record in sorted(records, key=lambda r: r.get("number") or 0):
        pmid = str(record.get("pmid", "")).strip()
        if pmid in abstracts and pmid not in seen:
            seen.add(pmid)
            kept.append(record)

    missing = [p for p in selected_pmids if p not in seen]
    if missing:
        print(f"  WARNING: {len(missing)} study/studies came back with no verdict.")

    return header(len(kept)) + factcheck_render.render_report(kept), kept
