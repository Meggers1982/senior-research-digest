"""One place for the rotation's topic names.

The rotation was reworded from "fall prevention" to "falls" partway through the
archive. The dashboard learned about that; trends.py did not, and it matches a
prior digest's Focus field by exact string. So the first "falls" run was told it
had no predecessor, one week after a "Fall Prevention" run it should have
compared against. Both layers import from here so the next rename cannot split
a beat in two again.
"""
from __future__ import annotations

TOPIC_ALIASES = {"fall prevention": "falls"}


def normalize_topic(topic: str) -> str:
    """Canonical name for a topic, whatever the rotation called it at the time."""
    cleaned = (topic or "").strip()
    return TOPIC_ALIASES.get(cleaned.lower(), cleaned)
