"""Render records to markdown, parse the markdown back, compare.

This is the test that closes the loop the verdict bug came through. The model no
longer writes the digest or the fact-check report — it returns records and Python
renders them — so the only remaining way for the dashboard to lose a field is for
the renderer and the parser to disagree. That disagreement is what this asserts
against, on both files, without an API key.
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard_data as bdd  # noqa: E402
import digest_generator  # noqa: E402
import digest_render  # noqa: E402
import fact_checker  # noqa: E402
import factcheck_render  # noqa: E402

PRIMARY = "older adults and seniors"
SECONDARY = "families, caregivers, and senior living professionals"

STUDIES = [
    {
        "headline": "Grip Strength Predicts Fracture Risk in Older Adults",
        "journal": "Age and Ageing",
        "published": "August 2026",
        "pmid": "40000001",
        "doi": "10.1093/ageing/afae001",
        "the_study": "Researchers followed 4,828 adults aged 65 and older for six years.",
        "why_it_matters": "Grip strength is cheap to measure in any clinic.",
        "story_angle_primary": "Ask for a grip-strength reading at your next visit.",
        "story_angle_secondary": "Operators can add the test to move-in assessments.",
        "caveats": "Observational design (cannot establish causation); single-country cohort.",
    },
    {
        # Pipes and newlines are the two things that would corrupt the citation
        # table or split a field across lines.
        "headline": "Sleep Trajectories | Dementia Onset",
        "journal": "Sleep\nMedicine",
        "published": "September 2026",
        "pmid": "40000002",
        "doi": "",
        "the_study": "An eight-year   analysis of  1,200 participants.",
        "why_it_matters": "Patterns beat single nights.",
        "story_angle_primary": "Keep a sleep diary before your appointment.",
        "story_angle_secondary": "Families can track changes over months.",
        "caveats": "",
    },
]

REPORT = [
    {"number": 1, "pmid": "40000001", "headline": "Grip Strength Predicts Fracture Risk",
     "verdict": "accurate", "notes": "", "issues": []},
    {"number": 2, "pmid": "40000002", "headline": "Sleep Trajectories | Dementia Onset",
     "verdict": "minor", "notes": "Rounded N.",
     "issues": [{"label": "Sample size", "severity": "Minor",
                 "as_written": "1,200 participants", "abstract_says": "1,187 participants",
                 "problem": "Rounded up.", "suggested_fix": "1,187 participants"}]},
    {"number": 3, "pmid": "40000003", "headline": "A Study With A Major Problem",
     "verdict": "significant", "notes": "Reverses the direction.",
     "issues": [{"label": "Direction", "severity": "Major",
                 "as_written": "reduced risk", "abstract_says": "increased risk",
                 "problem": "Opposite of the finding.", "suggested_fix": "increased risk"}]},
]


def digest_markdown(studies=STUDIES) -> str:
    header = (
        "# Senior Living Research Digest\n"
        "**Run date:** 2026-09-05 | **Coverage window:** Last 90 days\n"
        "**Journals searched:** 167 | **Articles screened:** 40\n"
        "**Focus:** sleep\n"
        f"**Primary audience:** {PRIMARY} | **Secondary audience:** {SECONDARY}\n\n---\n\n"
    )
    return header + digest_render.render_digest(studies, PRIMARY, SECONDARY)


class DigestRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markdown = digest_markdown()
        cls.parsed = bdd._parse_studies(cls.markdown.split("---", 1)[1])

    def test_every_study_survives_the_round_trip(self):
        self.assertEqual(len(self.parsed), len(STUDIES))

    def test_every_field_survives_the_round_trip(self):
        for original, parsed in zip(STUDIES, self.parsed):
            self.assertEqual(parsed["pmid"], original["pmid"])
            self.assertEqual(parsed["journal"], original["journal"].replace("\n", " "))
            self.assertEqual(parsed["published"], original["published"])
            self.assertEqual(parsed["the_study"], " ".join(original["the_study"].split()))
            self.assertEqual(parsed["why_it_matters"], original["why_it_matters"])
            self.assertEqual(parsed["story_angle_primary"], original["story_angle_primary"])
            self.assertEqual(parsed["story_angle_secondary"], original["story_angle_secondary"])

    def test_a_pipe_in_a_headline_does_not_break_the_citation_table(self):
        rows = bdd.CITATION_ROW_RE.findall(self.markdown)
        self.assertEqual(len(rows), len(STUDIES))
        self.assertEqual([r[0] for r in rows], [s["pmid"] for s in STUDIES])

    def test_a_missing_doi_renders_rather_than_disappearing(self):
        self.assertIn("Not available", self.markdown)

    def test_an_empty_caveat_gets_the_standard_phrase(self):
        self.assertIn("**Caveats:** None significant", self.markdown)

    def test_the_whole_file_parses_as_a_digest(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Senior Living Research Digest — Sleep — September 2026.md"
            path.write_text(self.markdown, encoding="utf-8")
            self.assertTrue(bdd.is_digest(path))
            run = bdd._parse_digest_file(path)
        self.assertEqual(run["study_count"], len(STUDIES))
        self.assertEqual(run["topic"], "sleep")
        self.assertEqual(run["journals_searched"], "167")
        # Scoring runs off the parsed record, so it has to survive too.
        self.assertTrue(all(s["band"] for s in run["studies"]))


class FactCheckRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markdown = (
            "# Fact-Check Report: Senior Living Research Digest — Sleep — September 2026\n"
            f"**Checked:** 2026-09-05 | **Studies reviewed:** {len(REPORT)}\n"
            f"**Primary audience:** {PRIMARY} | **Secondary audience:** {SECONDARY}\n\n---\n\n"
            + factcheck_render.render_report(REPORT)
        )

    def _parsed(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "report Fact Check.md"
            path.write_text(self.markdown, encoding="utf-8")
            return bdd._parse_fact_check(path)

    def test_every_verdict_survives_the_round_trip(self):
        """The exact failure: 22 of 52 reports lost every verdict to a heading
        the parser did not expect."""
        verdicts = self._parsed()["verdicts_by_pmid"]
        self.assertEqual(set(verdicts), {r["pmid"] for r in REPORT})

    def test_the_verdict_symbols_are_the_ones_the_dashboard_colours_on(self):
        verdicts = self._parsed()["verdicts_by_pmid"]
        self.assertIn("✅", verdicts["40000001"])
        self.assertIn("⚠️", verdicts["40000002"])
        self.assertIn("❌", verdicts["40000003"])

    def test_the_summary_counts_match_the_issues_rendered(self):
        summary = self._parsed()["summary"]
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_issues"], "2 (1 Minor, 0 Moderate, 1 Major)")
        self.assertEqual(summary["entries_requiring_revision"], "2")
        self.assertEqual(summary["entries_cleared"], "1")

    def test_the_reviewed_count_matches_the_verdicts(self):
        """Thirteen archived reports say "40" against ~20 verdicts, because the
        header counted abstracts sent rather than studies checked."""
        parsed = self._parsed()
        self.assertEqual(int(parsed["studies_reviewed"]), len(parsed["verdicts_by_pmid"]))

    def test_an_unknown_verdict_word_does_not_render_an_empty_badge(self):
        rendered = factcheck_render.render_report(
            [{"number": 1, "pmid": "40000001", "headline": "x",
              "verdict": "banana", "notes": "", "issues": []}])
        self.assertIn("✅", rendered)


class SchemaTests(unittest.TestCase):
    """The schemas and the renderers have to describe the same record."""

    def test_the_digest_schema_matches_what_the_renderer_reads(self):
        required = digest_generator.STUDY_SCHEMA["properties"]["studies"]["items"]["required"]
        self.assertEqual(set(required), set(digest_render.STUDY_FIELDS))

    def test_the_fact_check_schema_matches_what_the_renderer_reads(self):
        items = fact_checker.REPORT_SCHEMA["properties"]["studies"]["items"]
        self.assertEqual(set(items["required"]), set(factcheck_render.STUDY_FIELDS))
        issue = items["properties"]["issues"]["items"]
        self.assertEqual(set(issue["required"]), set(factcheck_render.ISSUE_FIELDS))

    def test_batches_are_small_enough_that_one_answer_is_one_turn(self):
        """A truncated JSON answer cannot be continued, so the guard is input
        size rather than a retry."""
        self.assertLessEqual(digest_generator.ABSTRACTS_PER_CALL, 15)
        self.assertLessEqual(fact_checker.STUDIES_PER_CALL, 15)


if __name__ == "__main__":
    unittest.main()
