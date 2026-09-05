"""Pitch-target suggestions drawn from the AgingWire publisher prospecting
databases.

The workbooks are the source of truth; `config/media/*.csv` here and in
agingwire-research-intelligence are both exports of them. Re-export to both when
a workbook changes rather than editing either CSV directly.

Matching differs from AgingWire's on purpose. Its topics are the same vocabulary
the outlets use ("housing", "workforce", "medicare"), so a direct term match
works. This digest's focus rotation is clinical -- osteoporosis, sarcopenia,
polypharmacy -- and no consumer publication lists "sarcopenia" in its coverage
blurb. Clinical topics are mapped to the consumer subject they belong to
instead, and where none fits the ranking falls back on how well an outlet takes
a data story.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
B2C_PATH = REPO_ROOT / "config" / "media" / "b2c_publications.csv"
B2B_PATH = REPO_ROOT / "config" / "media" / "b2b_publications.csv"
TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2, "Tier 4": 3, "Watchlist": 4}

# A clinical focus maps onto the subjects publications actually name. Terms are
# split because the distinction decides the ranking: nearly every publication in
# both registries covers "health" and "aging", so a list made only of those puts
# every outlet in the top band and the suggestion degrades to "any generalist".
# Only a SPECIFIC hit earns the top band.
TOPIC_TERMS = {
    "dementia": {
        "specific": ["dementia", "alzheim", "memory care", "cognitive", "brain"],
        "general": ["caregiv", "health", "aging"]},
    "cognitive decline": {
        "specific": ["dementia", "alzheim", "cognitive", "brain", "memory"],
        "general": ["caregiv", "health", "aging"]},
    "falls": {
        "specific": ["safety", "mobility", "fall", "home care", "rehab"],
        "general": ["caregiv", "aging", "senior living", "home"]},
    "osteoporosis": {
        "specific": ["bone", "women", "fitness", "exercise", "orthopedic"],
        "general": ["health", "aging", "wellness"]},
    "sarcopenia": {
        "specific": ["fitness", "exercise", "nutrition", "muscle", "rehab"],
        "general": ["health", "aging", "wellness"]},
    "cardiovascular disease": {
        "specific": ["heart", "cardiac", "cardiovascular", "stroke", "clinical"],
        "general": ["health", "aging", "wellness"]},
    "depression": {
        "specific": ["mental health", "behavioral", "psych", "loneliness", "social"],
        "general": ["caregiv", "health", "aging"]},
    "nutrition": {
        "specific": ["nutrition", "food", "dining", "diet", "culinary"],
        "general": ["health", "wellness", "aging"]},
    "sleep": {
        "specific": ["sleep", "insomnia", "clinical", "behavioral"],
        "general": ["health", "wellness", "aging"]},
    "palliative care": {
        "specific": ["hospice", "palliative", "end of life", "grief", "advance care"],
        "general": ["caregiv", "health", "clinical"]},
    "polypharmacy": {
        "specific": ["pharmacy", "medication", "medicare", "clinical", "prescri"],
        "general": ["health", "caregiv", "aging"]},
    "hearing loss": {
        "specific": ["hearing", "audio", "technology", "device", "assistive"],
        "general": ["health", "aging", "wellness"]},
    "vision loss": {
        "specific": ["vision", "eye", "low vision", "assistive", "technology"],
        "general": ["health", "aging", "wellness"]},
    # Not in the rotation; reachable only through a DIGEST_FOCUS override.
    "chronic pain": {
        "specific": ["pain", "rehab", "clinical", "therapy"],
        "general": ["health", "wellness", "aging"]},
    "incontinence": {
        "specific": ["continence", "clinical", "nursing", "products"],
        "general": ["health", "caregiv", "senior living"]},
}
GENERAL_TERMS = ["aging", "caregiv", "health", "senior"]


def _int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=4)
def _load(path: str, audience: str) -> tuple[dict, ...]:
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("Publication") or "").strip()
                if not name:
                    continue
                rows.append({
                    "publisher": name,
                    "audience": audience,
                    "category": (row.get("Category") or "").strip(),
                    "coverage": (row.get("Core Coverage") or "").strip(),
                    "reader": (row.get("Primary Audience") or "").strip(),
                    "rationale": (row.get("Why It Matters / Pitch Angle") or "").strip(),
                    "tier": (row.get("Priority Tier") or "").strip(),
                    "score": _int(row.get("Total Score")),
                    "data_fit": _int(row.get("Data-Story Fit (1-5)")),
                })
    except OSError as exc:
        # Returning () here meant a renamed or missing CSV produced a run with no
        # pitch targets, no error, and nothing to notice.
        raise RuntimeError(f"publisher registry unreadable: {path}") from exc
    if not rows:
        raise RuntimeError(f"publisher registry is empty: {path}")
    return tuple(rows)


def _stems(text: str) -> set:
    """Words, with a trailing plural "s" dropped so "fall" reaches "falls"."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in re.findall(r"[a-z]+", (text or "").lower())}


def _terms_for(subject_focus: str) -> dict:
    """(specific, general) terms for a focus.

    Matching is on whole words, not raw substrings. `key in focus or focus in
    key` also fired on fragments -- a focus of "ear" matched nothing sensible but
    a focus of "pain" would have picked up "chronic pain" either way, and there
    was no test to say which was intended.
    """
    focus = (subject_focus or "").strip().lower()
    if not focus:
        return {"specific": [], "general": list(GENERAL_TERMS)}
    focus_words = _stems(focus)
    for key, terms in TOPIC_TERMS.items():
        # The focus has to contain the whole key, not merely share a word with
        # it: "care" is not "palliative care", but "sleep quality" is "sleep"
        # and "fall" is "falls".
        if _stems(key) <= focus_words:
            return terms
    # An unmapped focus still has its own words worth trying, and they are the
    # most specific thing available.
    words = [w for w in focus_words if len(w) > 4]
    return {"specific": words, "general": list(GENERAL_TERMS)}


def _relevance(row: dict, terms: dict) -> tuple[int, int]:
    """(specific hits, general hits) against what the outlet says it covers."""
    blob = f"{row['coverage']} {row['category']} {row['publisher']}".lower()
    specific = sum(1 for t in terms.get("specific", []) if t in blob)
    general = sum(1 for t in terms.get("general", []) if t in blob)
    return specific, general


def suggest(subject_focus: str, audience: str, limit: int = 4,
            exclude: set[str] | None = None) -> list[dict]:
    """Publications that fit this digest's focus, best first.

    `exclude` drops outlets already found reporting the studies — pitching to
    the publication that just ran it is the one suggestion guaranteed wrong.
    """
    path = str(B2C_PATH if audience == "b2c" else B2B_PATH)
    rows = _load(path, audience)
    if not rows:
        return []
    terms = _terms_for(subject_focus)
    excluded = {e.strip().lower() for e in (exclude or set())}

    scored = [(_relevance(r, terms), r) for r in rows
              if r["publisher"].lower() not in excluded]
    matched = [(hits, r) for hits, r in scored if hits[0] or hits[1]]
    pool = matched or [((0, 0), r) for _, r in scored
                       if TIER_RANK.get(r["tier"], 9) <= 1]

    # Relevance bands rather than ranks directly. Ranking on the raw hit count
    # put Watchlist fitness titles above Next Avenue for osteoporosis; ranking on
    # data fit alone dropped Being Patient off a dementia run. Banding keeps a
    # topical specialist ahead of a generalist, then orders by how well the
    # outlet takes a data story.
    #
    # The top band needs a *specific* hit. Two general hits used to be enough,
    # and since almost every publication in both registries covers "health" and
    # "aging", that put nearly all of them in band 0 for every clinical topic.
    def band(hits: tuple[int, int]) -> int:
        specific, general = hits
        if specific >= 2:
            return 0
        if specific == 1:
            return 1
        return 2 if general >= 2 else 3

    pool.sort(key=lambda pair: (
        band(pair[0]), -pair[1]["data_fit"], TIER_RANK.get(pair[1]["tier"], 9),
        -pair[1]["score"], pair[1]["publisher"],
    ))
    return [r for _, r in pool[:limit]]


def describe(row: dict) -> str:
    tier = f", {row['tier']}" if row["tier"] else ""
    beat = row["coverage"] or row["category"]
    text = f"{row['publisher']} — {beat}{tier}"
    if row.get("rationale"):
        text += f". {row['rationale']}"
    return text


def candidate_block(subject_focus: str, exclude: set[str] | None = None) -> str:
    """The candidate list injected into the feature-pitch prompt."""
    consumer = suggest(subject_focus, "b2c", exclude=exclude)
    trade = suggest(subject_focus, "b2b", limit=3, exclude=exclude)
    if not consumer and not trade:
        return ""
    lines = ["Consumer:"] + [f"- {describe(r)}" for r in consumer]
    lines += ["Trade:"] + [f"- {describe(r)}" for r in trade]
    if exclude:
        lines.append(
            "Already reporting these studies, do not suggest: " + ", ".join(sorted(exclude))
        )
    return "\n".join(lines)
