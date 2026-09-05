"""The dashboard's data is regex-scraped out of markdown the model wrote.

Nothing has ever checked that the regexes still match what the model emits, and
that is exactly how a silent failure shipped: `FACT_CHECK_VERDICT_RE` hardcoded
`### Study N:` while the fact-checker emitted `## Study N:` in 22 of 52 reports,
so half the archive rendered with no verdict badge at all and the pipeline stayed
green throughout. These tests run the real parsers over the real committed
outputs, so drift fails here instead of on the page.
"""
import re
import pathlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard_data as bdd  # noqa: E402

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"
FACT_CHECK_FILES = sorted(OUTPUTS_DIR.glob("* Fact Check.md"))
DIGEST_FILES = sorted(
    p for p in OUTPUTS_DIR.glob("*.md")
    if not p.name.endswith("Fact Check.md") and bdd.is_digest(p)
)


class FactCheckParsingTests(unittest.TestCase):
    def test_there_are_fact_check_files_to_check(self):
        """A glob that silently matches nothing would make every test below pass."""
        self.assertTrue(FACT_CHECK_FILES)

    def test_a_verdict_is_found_for_every_pmid_the_file_plainly_contains(self):
        """An independent, regex-free cross-check of the regex-dependent path:
        grep the file for verdict lines and compare counts."""
        plain = re.compile(r"\*\*PMID:\*\*\s*(\d+)\s*\|\s*\*\*Verdict:\*\*")
        for path in FACT_CHECK_FILES:
            expected = set(plain.findall(path.read_text(encoding="utf-8")))
            if not expected:
                continue
            found = set(bdd._parse_fact_check(path)["verdicts_by_pmid"])
            self.assertEqual(found, expected, path.name)


class DigestFactCheckPairingTests(unittest.TestCase):
    """Every study the digest publishes should carry a fact-check verdict.

    Three archived runs violate this and cannot be repaired without regenerating
    them, so they are named here rather than weakening the assertion. A *new*
    mismatch fails the suite, which is the point.
    """

    # Two June digests were truncated mid-entry by the old max_tokens ceiling
    # (fixed 2026-07-10 by the continuation retry): the fact-check reviewed a
    # study whose text never made it into the digest file.
    #
    # The Vision Loss run is a model transcription slip -- the digest says PMID
    # 41365525 and its fact-check says 42365525 for the same study. One digit.
    KNOWN_UNPAIRED = {
        "Senior Living Research Digest — Dementia — June 2026.md",
        "Senior Living Research Digest — Depression — June 2026.md",
        "Senior Living Research Digest — Vision Loss — July 2026.md",
    }

    def test_every_published_study_has_a_verdict(self):
        for path in DIGEST_FILES:
            if path.name in self.KNOWN_UNPAIRED:
                continue
            run = bdd._parse_digest_file(path)
            verdicts = set((run["fact_check"] or {}).get("verdicts_by_pmid") or {})
            if not verdicts:
                continue
            unchecked = {s["pmid"] for s in run["studies"] if s["pmid"]} - verdicts
            self.assertEqual(unchecked, set(), path.name)

    def test_the_allowlist_does_not_outlive_the_files_it_names(self):
        """A renamed or regenerated file should drop out of the allowlist, not
        sit there silently excusing a run that no longer exists."""
        names = {p.name for p in DIGEST_FILES}
        self.assertEqual(self.KNOWN_UNPAIRED - names, set())


class DigestParsingTests(unittest.TestCase):
    def test_every_digest_yields_studies(self):
        for path in DIGEST_FILES:
            self.assertTrue(bdd._parse_digest_file(path)["studies"], path.name)

    def test_every_study_carries_the_fields_the_dashboard_renders(self):
        """"Why it matters" is deliberately not required: four pre-July digests
        were truncated partway through their last entry and lack it, but those
        cards still read fine. A study with no body at all is dropped instead."""
        for path in DIGEST_FILES:
            for study in bdd._parse_digest_file(path)["studies"]:
                for field in ("title", "pmid", "the_study"):
                    self.assertTrue(study.get(field), f"{path.name}: {field}")


class RunIndexTests(unittest.TestCase):
    """`topic-demand.md` is written into outputs/ by a different script and was
    being parsed as a digest, producing a dateless, studyless ghost run in the
    sidebar."""

    def test_only_digests_become_runs(self):
        """A run has to carry a date. It does not have to carry studies: the
        digest prompt says selecting fewer than were sent -- including none --
        is expected, and this assertion used to run in CI *before* the pipeline
        step, so the day after a zero-study digest was committed it would have
        blocked the pipeline from running again at all."""
        for run in bdd.build():
            self.assertTrue(run["run_date"], f"{run['id']} has no run date")
            self.assertEqual(run["study_count"], len(run.get("studies", [])),
                             f"{run['id']} miscounts its studies")

    def test_a_run_listed_in_hidden_json_is_left_out(self):
        """There was no way to hide a bad run at all. Nothing is deleted -- the
        markdown stays in outputs/ and removing the id brings the run back."""
        import json, tempfile, unittest.mock as m
        runs = bdd.build()
        self.assertTrue(runs, "no runs to hide")
        victim = runs[0]["id"]
        with tempfile.TemporaryDirectory() as raw:
            hidden = pathlib.Path(raw) / "hidden.json"
            hidden.write_text(json.dumps({"ids": [victim]}), encoding="utf-8")
            with m.patch.object(bdd, "HIDDEN_PATH", hidden):
                self.assertEqual(bdd.hidden_ids(), {victim})

    def test_an_unreadable_hidden_file_hides_nothing(self):
        import pathlib as pl, tempfile, unittest.mock as m
        with tempfile.TemporaryDirectory() as raw:
            hidden = pl.Path(raw) / "hidden.json"
            hidden.write_text("{not json", encoding="utf-8")
            with m.patch.object(bdd, "HIDDEN_PATH", hidden):
                self.assertEqual(bdd.hidden_ids(), set())

    def test_the_index_no_longer_carries_the_search_blobs(self):
        """They were 165 KB of a 183 KB file that loads on every page view."""
        import json
        index = json.loads((bdd.DASHBOARD_INDEX_PATH).read_text(encoding="utf-8"))
        self.assertTrue(index["runs"])
        self.assertNotIn("search", index["runs"][0])
        search = json.loads(bdd.SEARCH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(search), {r["id"] for r in index["runs"]})

    def test_the_topic_demand_report_is_not_a_run(self):
        self.assertNotIn("topic-demand", {r["id"] for r in bdd.build()})

    def test_topics_do_not_split_one_beat_in_two(self):
        """The rotation was reworded from "fall prevention" to "falls" partway
        through, which gave the topic filter two entries for one subject."""
        topics = {r["topic"] for r in bdd.build() if r["topic"]}
        self.assertNotIn("fall prevention", topics)


if __name__ == "__main__":
    unittest.main()
