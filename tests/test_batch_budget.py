"""Does a batch's answer actually fit in one turn?

complete_json refuses to stitch a truncated JSON array, so a batch that
overruns max_tokens loses its studies. The batch sizes were a convention -- the
only check on them asserted the constant was <= 15, which is not a measurement.

This measures the real thing it can measure: the size of the records the model
has to return, taken from the most recent runs in the committed archive. It
cannot see adaptive-thinking spend, so it holds the output to half the budget
and leaves the rest as headroom. A live check against the API is still owed.

Recent runs, not the whole archive. This used to take the max over every study
ever committed, and a max over a set that only grows can only go up: the
2026-09-07 run succeeded, committed one 2,708-character record, and every run
after it failed this check (MEA-373). A percentile over the whole archive would
be worse, not better. The generator that shipped 2026-09-05 writes records ~40%
longer than the one before it, so the archive's p95 (~1,840) sits below the
*median* of the current output (~2,080) and would pass a batch the live model
can overrun. The last RECENT_RUNS runs are what the current prompt and model
produce, and a single outlier ages out after one full focus rotation.

The workflow runs this as its own step, after the gating suite, and does not
fail the run on it. Its inputs are the pipeline's own output, so it must not be
able to stop the pipeline; and an overrun batch is split and retried rather
than lost, so a size that has drifted costs calls, not studies.
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


# One full pass of the 14-topic focus rotation, so every topic's typical record
# length is in the window.
RECENT_RUNS = 14


def _archive_studies():
    runs = [json.loads(path.read_text(encoding="utf-8"))
            for path in RUNS_DIR.glob("*.json")]
    runs.sort(key=lambda run: run.get("run_date") or "")
    for run in runs[-RECENT_RUNS:]:
        yield from run.get("studies", [])


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
