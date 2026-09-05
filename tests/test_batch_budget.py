"""Does a batch's answer actually fit in one turn?

complete_json refuses to stitch a truncated JSON array, so a batch that
overruns max_tokens loses its studies. The batch sizes were a convention -- the
only check on them asserted the constant was <= 15, which is not a measurement.

This measures the real thing it can measure: the size of the records the model
has to return, taken from every study in the committed archive. It cannot see
adaptive-thinking spend, so it holds the output to half the budget and leaves
the rest as headroom. A live check against the API is still owed.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import digest_generator  # noqa: E402
import fact_checker  # noqa: E402
import llm  # noqa: E402

RUNS_DIR = Path(__file__).resolve().parent.parent / "docs" / "data" / "runs"

# Pessimistic on purpose: dense JSON with punctuation and digits runs closer to
# 3 characters per token than the ~4 of ordinary prose.
CHARS_PER_TOKEN = 3.0
# Half the budget for the answer, half for thinking.
OUTPUT_SHARE = 0.5

DIGEST_FIELDS = ("pmid", "headline", "journal", "published", "doi", "the_study",
                 "why_it_matters", "story_angle_primary", "story_angle_secondary",
                 "caveats")


def _archive_studies():
    for path in sorted(RUNS_DIR.glob("*.json")):
        for study in json.loads(path.read_text(encoding="utf-8")).get("studies", []):
            yield study


def _worst_record_chars(build) -> int:
    sizes = [len(json.dumps(build(s), ensure_ascii=False)) for s in _archive_studies()]
    return max(sizes) if sizes else 0


class BatchBudgetTests(unittest.TestCase):
    def setUp(self):
        if not RUNS_DIR.exists() or not any(RUNS_DIR.glob("*.json")):
            self.skipTest("no archive to measure")

    def test_a_full_digest_batch_leaves_room_for_thinking(self):
        worst = _worst_record_chars(
            lambda s: {f: s.get("title" if f == "headline" else f, "") or ""
                       for f in DIGEST_FIELDS})
        tokens = (worst * digest_generator.ABSTRACTS_PER_CALL + 64) / CHARS_PER_TOKEN
        budget = llm.MAX_TOKENS * OUTPUT_SHARE
        self.assertLess(
            tokens, budget,
            f"a worst-case batch of {digest_generator.ABSTRACTS_PER_CALL} needs "
            f"~{tokens:.0f} output tokens against {budget:.0f}; lower "
            f"ABSTRACTS_PER_CALL or raise MAX_TOKENS")

    def test_a_full_fact_check_batch_leaves_room_for_thinking(self):
        # notes and issues are not kept in the archive, so allow generously for
        # what a verdict can carry beyond what is recorded.
        worst = _worst_record_chars(lambda s: {
            "number": s.get("number"), "pmid": s.get("pmid"),
            "headline": s.get("title", ""), "verdict": s.get("verdict", ""),
            "notes": "x" * 600, "issues": ["x" * 200] * 3})
        tokens = (worst * fact_checker.STUDIES_PER_CALL + 64) / CHARS_PER_TOKEN
        budget = llm.MAX_TOKENS * OUTPUT_SHARE
        self.assertLess(
            tokens, budget,
            f"a worst-case batch of {fact_checker.STUDIES_PER_CALL} needs "
            f"~{tokens:.0f} output tokens against {budget:.0f}")


if __name__ == "__main__":
    unittest.main()
