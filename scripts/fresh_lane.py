"""The "new this week" lane: what elderly-geriatric-digest did, done here.

The topic rotation reads 90 days of one subject. This lane reads the last seven
days of everything -- the 167 curated journals plus the 445 neurology, rehab,
rheumatology and geriatrics titles elderly-geriatric-digest searched -- and keeps
what the press has not already picked up. The two used to be separate repos that
shared 106 journals and 12 studies (MEA-573); the difference was always the
search, never the journal list, so the search is what moved.

Everything after selection is the same pipeline as a topic run: records, fact
check, coverage, trends, scoring, dashboard.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

import journals
import scoring
import web_coverage
from pubmed import search_by_issns, fetch_summaries

FOCUS_LABEL = "New this week"

DEFAULTS = {
    "days_back": 7,
    "max_abstracts": 40,
    # Checked before any abstract is fetched, so a study the press already has
    # never costs a model call. Forty-eight leaves room to drop a few and still
    # fill forty.
    "coverage_checks": 48,
    # News lags a paper by days, not hours; a 7-day news window would miss the
    # pickup of a study published on day one.
    "coverage_days": 14,
}

# PubMed's own publication types. Reviews stay: a review that says something
# new is as pitchable as a trial.
SKIP_PUBTYPES = {
    "editorial", "letter", "comment", "news", "biography", "case reports",
    "published erratum", "retraction of publication", "retracted publication",
    "expression of concern",
}

# From elderly-geriatric-digest. A title that names an animal model and no
# human population is not a study about older adults.
ANIMAL_ONLY_SIGNALS = (
    "in mice", "in rats", "in mouse", "in rat", "mouse model", "rat model",
    "murine", "rodent model", "in zebrafish", "in drosophila", "in c. elegans",
    "in vivo model", "animal model", "in vitro", "cell line", "in silico",
    "in monkeys", "in primates", "primate model", "in pigs", "in rabbits",
)
HUMAN_SIGNALS = (
    "patient", "human", "adult", "cohort", "clinical trial", "randomized",
    "participants", "men", "women", "population", "longitudinal",
    "cross-sectional", "survey", "residents", "people",
)

# Also from elderly-geriatric-digest, where it was the whole ranking. Here it is
# one term of three, and capped, so a title cannot win on adjectives alone.
NOVELTY_SIGNALS = (
    "first", "novel", "unexpected", "contrary", "paradox", "no evidence",
    "challenges", "reverses", "debunks", "replication", "previously unknown",
    "newly identified", "overturns", "failed to", "surpris", "counterintuitive",
    "new mechanism", "no significant", "no association", "opposite",
)

GUIDANCE = (
    "These abstracts are everything published in the last seven days across "
    "aging journals and general medical, neurology, rehabilitation and "
    "rheumatology journals -- not a topic search. Write up only studies whose "
    "findings bear on older adults or the people who care for them; a study "
    "whose population is entirely under 65, with no older subgroup, is not one. "
    "Favor findings that are counterintuitive, overturn earlier research, or are "
    "the first of their kind."
)

_PMID_IN_DIGEST = re.compile(r"\*\*PMID:\*\*\s*(\d+)")


def settings(config: dict) -> dict:
    return {**DEFAULTS, **(config.get("new_this_week") or {})}


def prior_pmids(outputs_dir: Path) -> set[str]:
    """Every PMID any earlier digest has written up, in either lane.

    The window is seven days and the lane runs daily, so without this the same
    study would be written up on up to seven consecutive days.
    """
    seen: set[str] = set()
    for path in outputs_dir.glob("*.md"):
        if path.name.endswith("Fact Check.md"):
            continue
        try:
            seen.update(_PMID_IN_DIGEST.findall(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return seen


def is_animal_only(title: str) -> bool:
    text = (title or "").lower()
    return (any(s in text for s in ANIMAL_ONLY_SIGNALS)
            and not any(s in text for s in HUMAN_SIGNALS))


def novelty(title: str) -> int:
    text = (title or "").lower()
    return min(2, sum(1 for s in NOVELTY_SIGNALS if s in text))


def rank_key(record: dict) -> tuple:
    """Higher sorts first. Design and journal from the same functions that score
    the finished digest, so the lane picks on the terms it is judged on."""
    title = record.get("title", "")
    _, design = scoring.evidence_type(title)
    _, tier = scoring.journal_tier(record.get("fulljournalname") or record.get("source", ""))
    return (2 * novelty(title) + design + tier, record.get("sortpubdate", ""))


def screen(summaries: dict, exclude: set[str]) -> tuple[list[dict], dict]:
    """Candidates worth an abstract, best first, and a count of what was dropped."""
    dropped = {"already_written_up": 0, "publication_type": 0, "no_abstract": 0,
               "animal_only": 0}
    kept = []
    for pmid, record in summaries.items():
        if not isinstance(record, dict) or pmid == "uids" or record.get("error"):
            continue
        title = (record.get("title") or "").strip()
        if not title:
            continue
        if pmid in exclude:
            dropped["already_written_up"] += 1
            continue
        if SKIP_PUBTYPES & {p.lower() for p in record.get("pubtype") or []}:
            dropped["publication_type"] += 1
            continue
        if "Has Abstract" not in (record.get("attributes") or []):
            dropped["no_abstract"] += 1
            continue
        if is_animal_only(title):
            dropped["animal_only"] += 1
            continue
        kept.append({**record, "pmid": pmid, "title": title})
    kept.sort(key=rank_key, reverse=True)
    return kept, dropped


def drop_widely_covered(candidates: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """Check the top of the list against Google News and keep what is still open.

    elderly-geriatric-digest dropped any study with 3+ news hits. This uses the
    same state the finished digest reports -- 3+ distinct outlets with a
    matching headline is "widely_reported" -- so the two cannot disagree, and
    the results land in the PMID cache the post-generation check reads.
    """
    pool = candidates[:cfg["coverage_checks"]]
    coverage = web_coverage.check_digest(
        [(c["pmid"], c["title"]) for c in pool],
        days_back=cfg["coverage_days"],
        limit=cfg["coverage_checks"],
        wall_seconds=300,
    )
    by_pmid = coverage.get("by_pmid") or {}
    open_ = [c for c in pool
             if (by_pmid.get(c["pmid"]) or {}).get("state") != "widely_reported"]
    selected = open_[:cfg["max_abstracts"]]
    # A short pool is topped up from below the checked range rather than left
    # short; the digest's own coverage pass checks those afterwards.
    if len(selected) < cfg["max_abstracts"]:
        selected += candidates[len(pool):len(pool) + cfg["max_abstracts"] - len(selected)]
    coverage["dropped_widely_reported"] = len(pool) - len(open_)
    return selected, coverage


# ── Feedback from the shared dashboard ──────────────────────────────────────
#
# elderly-geriatric-digest nudged its model with what she had saved and passed
# on. It read those from Supabase, which the dashboard stopped writing to on
# 2026-09-02 when status moved to a shared Neon database -- so from then on it
# was learning from frozen feedback. The dashboard's own API is the live copy.
DASHBOARD_URL = "https://research-digest-dashboard.vercel.app"
FEEDBACK_SOURCES = ("senior-research", "elderly-geriatric")
POSITIVE = {"saved", "pitched"}
NEGATIVE = {"deleted", "passed"}


def _get_json(url: str, timeout: float = 15):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def feedback_note(fetch=_get_json, limit: int = 8) -> str:
    """A soft steer from her saves and passes, or "" if anything is missing."""
    try:
        rows = fetch(f"{DASHBOARD_URL}/api/status")
    except Exception as exc:  # noqa: BLE001 -- feedback is optional
        print(f"  Feedback: status API unavailable ({type(exc).__name__}); skipping.")
        return ""
    saved, passed = [], []
    for row in rows if isinstance(rows, list) else []:
        source, _, pmid = str(row.get("study_id", "")).partition(":")
        if source not in FEEDBACK_SOURCES or not pmid.isdigit():
            continue
        status = row.get("status")
        (saved if status in POSITIVE else passed if status in NEGATIVE else []).append(pmid)
    if not saved and not passed:
        return ""

    headlines: dict[str, str] = {}
    for source in FEEDBACK_SOURCES:
        try:
            data = fetch(f"{DASHBOARD_URL}/data/{source}.json")
        except Exception:  # noqa: BLE001 -- a source file that does not exist yet
            continue
        for study in (data or {}).get("studies", []):
            if study.get("pmid") and study.get("headline"):
                headlines.setdefault(str(study["pmid"]), study["headline"][:100])

    # The API returns no timestamps. PMIDs are issued in order, so the highest
    # are the newest -- a fair proxy for "recent".
    def examples(pmids):
        ordered = sorted(set(pmids), key=int, reverse=True)
        return [headlines[p] for p in ordered if p in headlines][:limit]

    liked, disliked = examples(saved), examples(passed)
    if not liked and not disliked:
        return ""
    lines = ["Her past feedback on this beat. A soft signal when choosing what to "
             "write up; never leave out a strong study because of it."]
    if liked:
        lines.append("She saved or pitched:")
        lines += [f"- {h}" for h in liked]
    if disliked:
        lines.append("She passed on:")
        lines += [f"- {h}" for h in disliked]
    print(f"  Feedback: {len(liked)} saved and {len(disliked)} passed example(s).")
    return "\n".join(lines)


# ── The lane ─────────────────────────────────────────────────────────────────

def gather(config: dict, outputs_dir: Path, ncbi_api_key: str | None = None) -> dict:
    """Search, screen and select. Returns what main.py needs to write the digest."""
    cfg = settings(config)
    plain, qualified = journals.new_this_week_issns()
    print(f"Journals  : {len(plain)} searched as-is, {len(qualified)} held to "
          f"older-adult studies ({len(plain) + len(qualified)} total)")

    # No cap worth hitting: seven days of 600 journals is a few hundred papers,
    # and ranking needs to see all of them, not the first 200.
    found = []
    for issns, qualifier in ((plain, ""), (qualified, journals.OLDER_ADULT_QUALIFIER)):
        found += search_by_issns(issns=issns, days_back=cfg["days_back"],
                                 max_per_batch=25, max_total=5000,
                                 per_batch_cap=1000, qualifier=qualifier,
                                 ncbi_api_key=ncbi_api_key)
    pmids = list(dict.fromkeys(found))
    print(f"Found {len(pmids)} articles from the last {cfg['days_back']} days")

    summaries = fetch_summaries(pmids, ncbi_api_key=ncbi_api_key) if pmids else {}
    candidates, dropped = screen(summaries, prior_pmids(outputs_dir))
    print(f"Screened to {len(candidates)} candidates "
          + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in dropped.items() if v))

    selected, coverage = drop_widely_covered(candidates, cfg) if candidates else ([], {})
    if coverage.get("skipped_reason"):
        print(f"Coverage pre-check: skipped -- {coverage['skipped_reason']}")
    elif coverage:
        print(f"Coverage pre-check: {coverage.get('checked', 0)} checked, "
              f"{coverage.get('cached', 0)} cached, {coverage.get('skipped', 0)} skipped; "
              f"{coverage['dropped_widely_reported']} dropped as widely reported")

    return {
        "settings": cfg,
        "pmids": [c["pmid"] for c in selected],
        "summaries": summaries,
        "journal_count": len(plain) + len(qualified),
        "found": len(pmids),
    }
