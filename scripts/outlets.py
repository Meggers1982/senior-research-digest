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

# A clinical focus maps onto the subjects publications actually name.
TOPIC_TERMS = {
    "dementia": ["dementia", "alzheim", "memory care", "cognitive", "caregiv"],
    "cognitive decline": ["dementia", "alzheim", "cognitive", "brain"],
    "falls": ["caregiv", "safety", "aging", "home", "mobility", "senior living"],
    "osteoporosis": ["health", "aging", "women", "wellness", "fitness"],
    "sarcopenia": ["health", "fitness", "aging", "nutrition", "wellness"],
    "cardiovascular disease": ["health", "aging", "wellness"],
    "depression": ["mental health", "health", "caregiv", "aging"],
    "nutrition": ["nutrition", "food", "dining", "health", "wellness"],
    "sleep": ["health", "wellness", "aging"],
    "palliative care": ["hospice", "palliative", "end of life", "caregiv", "health"],
    "polypharmacy": ["health", "medicare", "pharmacy", "caregiv", "clinical"],
    "hearing loss": ["health", "aging", "technology", "wellness"],
    "vision loss": ["health", "aging", "wellness"],
    "chronic pain": ["health", "wellness", "aging"],
    "incontinence": ["health", "caregiv", "senior living", "clinical"],
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
    except OSError:
        return ()
    return tuple(rows)


def _terms_for(subject_focus: str) -> list[str]:
    focus = (subject_focus or "").strip().lower()
    if not focus:
        return list(GENERAL_TERMS)
    for key, terms in TOPIC_TERMS.items():
        if key in focus or focus in key:
            return terms
    # An unmapped focus still has its own words worth trying.
    words = [w for w in re.findall(r"[a-z]+", focus) if len(w) > 4]
    return words + GENERAL_TERMS


def _relevance(row: dict, terms: list[str]) -> int:
    blob = f"{row['coverage']} {row['category']} {row['publisher']}".lower()
    return sum(1 for t in terms if t in blob)


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
    matched = [(n, r) for n, r in scored if n > 0]
    pool = matched or [(1, r) for _, r in scored if TIER_RANK.get(r["tier"], 9) <= 1]

    # Relevance bands rather than ranks directly. Ranking on the raw hit count
    # put Watchlist fitness titles above Next Avenue for osteoporosis; ranking on
    # data fit alone dropped Being Patient off a dementia run. Banding keeps a
    # topical specialist ahead of a generalist, then orders by how well the
    # outlet takes a data story.
    def band(hits: int) -> int:
        return 0 if hits >= 2 else 1

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
