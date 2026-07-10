"""Fact-check a research digest against original PubMed abstracts using Claude."""

import re
from datetime import datetime
from typing import Optional

import anthropic

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
   no overgeneralisation beyond the study population; "Why it matters" doesn't leap
   beyond what the data support
4. **Story angles** — no clinical recommendations from preliminary or observational data;
   no hype language ("breakthrough", "could reverse", "eliminates", "proven to prevent");
   audience language appropriate for the stated primary/secondary audiences

## Output format per study

### Study [#]: [Headline from digest]
**PMID:** [ID] | **Verdict:** ✅ Accurate / ⚠️ Minor issues / ❌ Significant issues

[If no issues:]
No factual errors found. Framing is consistent with the abstract.

[If issues found:]
**Issue [A]. [Short label]** — Severity: Minor / Moderate / Major

- **As written:** "[exact quote from digest]"
- **Abstract says:** "[exact quote or close paraphrase]"
- **Problem:** Plain-language explanation of the discrepancy.
- **Suggested fix:** "[Corrected version of the text]"

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

After all entries, write:

## Issue Summary

| Study # | Headline | Verdict | Notes |
|---------|----------|---------|-------|

**Total issues:** [N] ([N] Minor, [N] Moderate, [N] Major)
**Entries requiring revision:** [N]
**Entries cleared:** [N]
"""

MAX_CONTINUATIONS = 3
CONTINUATION_PROMPT = (
    "Continue exactly where you left off. Do not repeat any content already "
    "written, and do not restart from the beginning."
)

# Cache the (static) system prompt so continuation retries re-read it from
# cache instead of reprocessing it at full price on every retry.
SYSTEM_PROMPT_BLOCKS = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _extract_header_field(digest: str, field: str) -> str:
    """Extract a labelled field from the digest header."""
    match = re.search(rf"\*\*{re.escape(field)}:\*\*\s*([^\n|]+)", digest)
    return match.group(1).strip() if match else ""


def run_fact_check(
    digest_content: str,
    selected_pmids: list[str],
    ncbi_api_key: Optional[str],
    anthropic_api_key: str,
    model: str = "claude-opus-4-5",
    subject_focus: str = "",
) -> str:
    """Fact-check a digest and return the fact-check report as markdown."""

    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Parse header fields from the digest
    primary_audience = _extract_header_field(digest_content, "Primary audience")
    secondary_audience = _extract_header_field(digest_content, "Secondary audience")
    category_line = (
        f"Senior Living Research Digest{' — ' + subject_focus.title() if subject_focus else ''}"
    )

    run_date = datetime.now().strftime("%Y-%m-%d")
    month_year = datetime.now().strftime("%B %Y")

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

    abstracts_block = "\n\n".join(
        f"--- PMID {pmid} ---\n{text}" for pmid, text in abstracts.items()
    )

    report_header = (
        f"# Fact-Check Report: {category_line} — {month_year}\n"
        f"**Checked:** {run_date} | **Studies reviewed:** {len(selected_pmids)}\n"
        f"**Primary audience:** {primary_audience} | **Secondary audience:** {secondary_audience}\n\n"
        "---\n\n"
    )

    user_message = (
        f"Fact-check the digest below against the original abstracts.\n\n"
        f"**Primary audience:** {primary_audience}\n"
        f"**Secondary audience:** {secondary_audience}\n\n"
        f"{'=' * 60}\n"
        f"DIGEST TO CHECK:\n\n"
        f"{digest_content}\n\n"
        f"{'=' * 60}\n"
        f"ORIGINAL ABSTRACTS:\n\n"
        f"{abstracts_block}\n"
        f"{'=' * 60}"
    )

    # The initial message is large (full digest + all original abstracts) — mark
    # it cacheable alongside the system prompt so retries below don't reprocess
    # it at full price.
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": user_message, "cache_control": {"type": "ephemeral"}}],
        }
    ]
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT_BLOCKS,
        messages=messages,
    )
    chunk = response.content[0].text if response.content else ""
    report_body = chunk

    continuations = 0
    while response.stop_reason == "max_tokens" and continuations < MAX_CONTINUATIONS:
        # Echo back only THIS turn's partial text as the assistant message —
        # not the full accumulated report — so history mirrors what actually
        # happened turn-by-turn and doesn't duplicate content.
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": CONTINUATION_PROMPT})
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT_BLOCKS,
            messages=messages,
        )
        chunk = response.content[0].text if response.content else ""
        report_body += chunk
        continuations += 1

    if response.stop_reason == "max_tokens":
        print(
            "  WARNING: fact-check response still truncated after "
            f"{MAX_CONTINUATIONS} continuation(s) — output may be incomplete."
        )

    return report_header + report_body
