"""How pitchable is a study?

Deliberately deterministic. Every input here is something the pipeline already
holds — the journal it ran in, when it published, what design the write-up
describes, how many people were in it, whether the press has already had it, and
what the fact-checker said. Nothing is asked of a model, because a score a model
assigns cannot be reproduced on a re-run of the same abstract and cannot be
unit-tested.

The weights exist because an unweighted sum does not discriminate: the same
mistake in agingwire-research-intelligence put 65 of 85 items on an identical
score. Bands, not ranks, are what the number can honestly support — two studies
three points apart are not meaningfully different.
"""
from __future__ import annotations

import re

# Weighted 0-5 components. Coverage and design carry the most because they are
# the two questions that actually decide whether a pitch is live: is the story
# still open, and is the evidence strong enough to build one on.
WEIGHTS = {
    "evidence_type": 3,
    "coverage_gap": 3,
    "journal_tier": 2,
    "recency": 2,
    "sample_size": 1,
    "accuracy": 1,
}

# Tuned against the 1,122 studies in the archive so each band actually holds a
# distinct slice of it. A first pass put 53% in one band, which filters nothing.
SCORE_BANDS = ((82, "Lead"), (72, "Strong"), (62, "Worth a look"), (0, "Background"))


def score_band(score) -> str:
    for floor, name in SCORE_BANDS:
        if score >= floor:
            return name
    return "Background"


# Strongest first, matching SCORE_BANDS.
BAND_ORDER = [name for _, name in SCORE_BANDS]
# The best a study can be called when nobody checked whether the press already
# ran it. "Lead" is a claim that the story is open, and that is precisely the
# thing an unchecked study has no evidence for.
UNCHECKED_COVERAGE_CEILING = "Strong"


def cap_band(band: str, ceiling: str) -> str:
    """Return whichever of the two is weaker."""
    try:
        return band if BAND_ORDER.index(band) >= BAND_ORDER.index(ceiling) else ceiling
    except ValueError:
        return band


def story_score(components: dict) -> int:
    """Weighted components on 0-5, rescaled to 0-100.

    A component whose value is None was not measured, and it is dropped from
    both halves of the fraction rather than scored as a middling 2. That keeps a
    score comparable across runs: coverage was never actually checked before
    2026-09, and folding "we didn't look" in as a mid value would have made every
    study jump about 15 points the day the check was switched on.
    """
    known = {k: v for k, v in components.items() if v is not None and k in WEIGHTS}
    if not known:
        return 0
    total = sum(WEIGHTS[k] * min(5, max(0, v)) for k, v in known.items())
    return round(100 * total / (5 * sum(WEIGHTS[k] for k in known)))


# ---------------------------------------------------------------- evidence type

# Ordered: the first pattern that matches wins, so the strongest design a
# write-up claims is the one recorded.
EVIDENCE_PATTERNS = (
    ("meta-analysis", 5, r"meta-analy|systematic review|pooled (?:analysis|data) (?:of|from)"),
    ("randomized trial", 5,
     r"randomi[sz]ed|randomly assigned|placebo-controlled|\bRCT\b|"
     r"clinical trial|intervention group|assigned to (?:receive|either)"),
    # Anything that follows people over time. The write-ups bury the follow-up
    # window behind long parentheticals, so this cannot be a tight window match.
    ("cohort", 4,
     r"cohort|longitudinal|prospectiv|retrospectiv|target trial emulation|"
     r"followed[^.]{0,160}?\b(?:for|over|up to)\b[^.]{0,40}?\d|"
     r"\b(?:over|across|during)\s+(?:up to\s+)?[\d.]+[-\s]*(?:year|month|decade)|"
     r"health records of|claims data|registry (?:of|data)|electronic health record"),
    ("case-control", 3,
     r"case-control|matched controls|age-matched|matched (?:on|for) age|"
     r"compared[^.]{0,80}\bcontrols?\b"),
    ("cross-sectional", 2,
     r"cross-sectional|survey|nationally representative|\bNHANES\b|"
     r"at a single time|single time point|questionnaire"),
    ("modelling", 2, r"simulat|model(?:l)?ing study|projected|microsimulation"),
    ("preclinical", 1, r"\bmice\b|\brats\b|animal model|in vitro|cell culture"),
    # Still observational, just unlabelled: an association measured in a named
    # group of people. Scored below a cohort, above an unreadable write-up.
    ("observational", 3,
     r"\bassociated with\b|\blinked to\b|\bexamined\b|\bassessed\b|\bcompared\b|"
     r"analy[sz]ed data|among [\d,]{3,}"),
)


def evidence_type(text: str) -> tuple[str, int]:
    """(label, 0-5). "unspecified" scores 2 — a neutral middle, not a penalty,
    because a write-up that omits the design is not evidence of a weak one."""
    blob = (text or "").lower()
    for label, points, pattern in EVIDENCE_PATTERNS:
        if re.search(pattern, blob):
            return label, points
    return "unspecified", 2


# ------------------------------------------------------------------ sample size

_N_PATTERNS = (
    r"\b[nN]\s*=\s*([\d,]{2,})",
    r"\b([\d,]{3,})\s+(?:adults|participants|patients|older adults|people|residents|women|men)\b",
    r"\bdata from\s+([\d,]{3,})\b",
)


def sample_size(text: str) -> tuple[int | None, int]:
    """(participants, 0-5). Unknown scores 2, the same neutral as an unstated
    design — rewarding "unknown" is how ties get manufactured."""
    blob = text or ""
    best = None
    for pattern in _N_PATTERNS:
        for raw in re.findall(pattern, blob):
            try:
                value = int(raw.replace(",", ""))
            except ValueError:
                continue
            if value > (best or 0):
                best = value
    if best is None:
        return None, 2
    for floor, points in ((10000, 5), (1000, 4), (300, 3), (100, 2), (0, 1)):
        if best >= floor:
            return best, points
    return best, 1


# ----------------------------------------------------------------- journal tier

# Not all 167 curated journals are tiered by hand. These are the ones whose name
# alone changes how a pitch lands; everything else is a credible specialty
# journal and scores the same middle value.
TIER_1 = (
    "new england journal of medicine", "lancet", "jama", "bmj", "nature",
    "journals of gerontology", "age and ageing", "journal of the american geriatrics society",
    "alzheimer's & dementia", "alzheimers & dementia", "annals of internal medicine",
)
TIER_2 = (
    "jama network open", "journal of the american medical directors association",
    "gerontologist", "neurology", "circulation", "diabetes care", "sleep",
    "journal of bone and mineral research", "osteoporosis international",
    "geroscience", "aging cell", "journal of affective disorders",
)


def journal_tier(name: str) -> tuple[int, int]:
    """(tier, 0-5). Tier 3 is the default and is not a criticism."""
    blob = (name or "").strip().strip("*").lower()
    if not blob:
        return 3, 2
    if any(t in blob for t in TIER_1):
        return 1, 5
    if any(t in blob for t in TIER_2):
        return 2, 4
    return 3, 3


# --------------------------------------------------------------------- recency

_MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december"]
_MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES, start=1)}
# PubMed abbreviates as often as it spells out, and an unrecognised month is
# indistinguishable from an unreadable date once it reaches recency().
_MONTHS |= {m[:3]: i for i, m in enumerate(_MONTH_NAMES, start=1)}

# One pattern for both shapes the archive actually contains: "August 2026" and
# "April 20, 2026". The day is optional, and it is the reason this needs saying
# at all -- the older pattern required the month to sit directly against the
# year, so every date carrying a day fell past it.
_MONTH_YEAR = re.compile(r"([a-z]+)\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(\d{4})")


def _published_month(published: str) -> tuple[int, int] | None:
    """(year, month), or None when the string does not carry both.

    Scanning every match rather than taking the first means a leading word that
    happens to precede a year -- "Published online 2026 ..." -- cannot shadow the
    real month further along.
    """
    text = (published or "").strip().lower()
    for match in _MONTH_YEAR.finditer(text):
        month = _MONTHS.get(match.group(1))
        if month:
            return int(match.group(2)), month
    match = re.search(r"(\d{4})-(\d{2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    # A bare year used to be reported as June, which is a fabricated month
    # dressed as a measurement: "April 20, 2026" scored as though it published
    # in June. recency() already treats an unreadable date as a real gap, so a
    # year with no month is handed back as one.
    return None


def recency(published: str, run_date: str) -> int:
    """0-5 by months between publication and the run. Undated scores 0, not a
    middle value: a date the pipeline could not read is a real gap."""
    published_at = _published_month(published)
    run_at = _published_month(run_date) or _published_month((run_date or "")[:7])
    if not published_at or not run_at:
        return 0
    months = (run_at[0] - published_at[0]) * 12 + (run_at[1] - published_at[1])
    if months < 0:          # ahead-of-print carries a future cover date
        return 5
    for limit, points in ((1, 5), (3, 4), (6, 3), (12, 2), (24, 1)):
        if months <= limit:
            return points
    return 0


# --------------------------------------------------------------- coverage & QA

COVERAGE_POINTS = {
    "unreported": 5,
    "lightly_reported": 2,
    "widely_reported": 0,
}


def coverage_gap(state: str | None) -> int | None:
    """0-5, or None when nobody looked.

    Absence of coverage is not evidence of a gap — it is usually evidence that
    nobody looked. Crediting it as one is what inflated the sibling repo's scores
    until 89 of its 132 publishers turned out to have no working feed. An
    unchecked study drops the component instead of guessing at it.
    """
    if not state:
        return None
    return COVERAGE_POINTS.get(state)


def accuracy(verdict: str | None) -> int | None:
    """0-5 from the fact-checker's verdict symbol, or None if it never ran."""
    text = verdict or ""
    if not text.strip():
        return None
    if "❌" in text:
        return 0
    if "⚠️" in text or "⚠" in text:
        return 2
    if "✅" in text:
        return 5
    return 3


# ------------------------------------------------------------------- the scorer


def score_study(study: dict, run_date: str = "", coverage_state=None, verdict=None) -> dict:
    """Return the score, its band and every component that produced them.

    The components are kept because a bare number is not reviewable — when a
    study ranks oddly, the row shows which part is responsible.
    """
    body = " ".join(filter(None, [
        study.get("the_study", ""), study.get("why_it_matters", ""),
        study.get("caveats", ""), study.get("title", ""),
    ]))

    design, design_points = evidence_type(body)
    participants, size_points = sample_size(body)
    tier, tier_points = journal_tier(study.get("journal", ""))

    components = {
        "evidence_type": design_points,
        "coverage_gap": coverage_gap(coverage_state),
        "journal_tier": tier_points,
        "recency": recency(study.get("published", ""), run_date),
        "sample_size": size_points,
        "accuracy": accuracy(verdict),
    }
    score = story_score(components)
    # story_score drops an unmeasured component from both halves of the
    # fraction, which is right -- but it means a study can reach 100 on the
    # strength of everything except the heaviest question nobody asked. Two
    # studies in the archive did exactly that. The number stays as measured, so
    # the row is still reviewable; the band, which is what gets filtered and
    # pitched on, does not claim more than the evidence supports.
    band = score_band(score)
    if components["coverage_gap"] is None:
        band = cap_band(band, UNCHECKED_COVERAGE_CEILING)
    return {
        "score": score,
        "band": band,
        "evidence_type": design,
        "sample_size": participants,
        "journal_tier": tier,
        "coverage_state": coverage_state or "",
        "components": components,
    }
