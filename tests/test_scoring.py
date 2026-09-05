"""The scorer is the only part of this pipeline whose output is a judgement.

It is pure Python precisely so it can be tested: the same study scores the same
way every run, and a change to a weight shows up here rather than as a quietly
reordered dashboard.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scoring  # noqa: E402


def study(**kw):
    base = {"title": "A study", "journal": "Age and Ageing",
            "published": "August 2026", "the_study": "", "why_it_matters": "",
            "caveats": ""}
    base.update(kw)
    return base


class EvidenceTypeTests(unittest.TestCase):
    def test_the_strongest_claimed_design_wins(self):
        text = "A meta-analysis of 12 randomized trials in a longitudinal cohort"
        self.assertEqual(scoring.evidence_type(text)[0], "meta-analysis")

    def test_designs_are_recognised_from_how_the_write_ups_actually_read(self):
        cases = {
            "Researchers randomly assigned 240 adults to resistance training": "randomized trial",
            "Researchers followed 482 older adults (mean age 68, 84% women) for up to 15 years":
                "cohort",
            "Using a target trial emulation approach, they compared outcomes": "cohort",
            "Analyzing nationally representative NHANES data from 18,434 adults":
                "cross-sectional",
            "Researchers compared MRI scans from 176 age-matched cognitively normal adults":
                "case-control",
            "In a study of mice, the compound reduced amyloid": "preclinical",
        }
        for text, expected in cases.items():
            self.assertEqual(scoring.evidence_type(text)[0], expected, text[:40])

    def test_an_unreadable_write_up_is_neutral_not_punished(self):
        label, points = scoring.evidence_type("Something happened.")
        self.assertEqual(label, "unspecified")
        self.assertEqual(points, 2)


class SampleSizeTests(unittest.TestCase):
    def test_the_largest_stated_number_is_taken(self):
        n, _ = scoring.sample_size("Of 12,000 adults screened, 1,200 participants enrolled")
        self.assertEqual(n, 12000)

    def test_n_equals_notation(self):
        self.assertEqual(scoring.sample_size("(N = 4,828)")[0], 4828)

    def test_unknown_is_neutral_rather_than_zero(self):
        n, points = scoring.sample_size("Researchers looked at some people.")
        self.assertIsNone(n)
        self.assertEqual(points, 2)


class RecencyTests(unittest.TestCase):
    def test_a_recent_paper_outscores_an_old_one(self):
        self.assertGreater(
            scoring.recency("August 2026", "2026-09-05"),
            scoring.recency("August 2024", "2026-09-05"),
        )

    def test_an_ahead_of_print_cover_date_is_not_penalised(self):
        self.assertEqual(scoring.recency("November 2026", "2026-09-05"), 5)

    def test_a_date_carrying_a_day_reads_as_its_real_month(self):
        """71% of the 1,122 studies in the archive publish as "Month D, YYYY".
        The month sat one comma away from the year, the pattern required them
        adjacent, and every one of them fell through to a branch that reported
        June."""
        self.assertEqual(scoring._published_month("April 20, 2026"), (2026, 4))
        self.assertEqual(scoring._published_month("August 2026"), (2026, 8))
        self.assertEqual(scoring._published_month("Published online April 3rd, 2026"),
                         (2026, 4))

    def test_an_abbreviated_month_is_understood(self):
        self.assertEqual(scoring._published_month("Apr 20, 2026"), (2026, 4))

    def test_a_year_with_no_month_is_not_reported_as_june(self):
        self.assertIsNone(scoring._published_month("2026"))

    def test_a_day_dated_paper_is_not_flattered_by_a_fabricated_month(self):
        """April read as June made a paper look two months fresher than it is,
        which is enough to cross a recency bucket."""
        self.assertEqual(scoring.recency("April 20, 2026", "2026-09-05"),
                         scoring.recency("April 2026", "2026-09-05"))

    def test_an_unreadable_date_scores_zero_not_a_middle_value(self):
        """A date the pipeline could not read is a real gap, unlike a design it
        could not read, which merely wasn't stated."""
        self.assertEqual(scoring.recency("", "2026-09-05"), 0)


class CoverageTests(unittest.TestCase):
    def test_nobody_looked_is_not_the_same_as_nobody_covered_it(self):
        self.assertIsNone(scoring.coverage_gap(None))
        self.assertEqual(scoring.coverage_gap("unreported"), 5)

    def test_an_unmeasured_component_leaves_the_score_comparable(self):
        """Coverage was never actually checked before 2026-09. If "unchecked"
        scored as a middle value, every study would have jumped the day the
        check was switched on."""
        components = {"evidence_type": 4, "journal_tier": 3, "recency": 4,
                      "sample_size": 3, "accuracy": 5, "coverage_gap": None}
        without = scoring.story_score(components)
        with_mid = scoring.story_score({**components, "coverage_gap": 3})
        self.assertNotEqual(without, 0)
        # Dropping the component is not the same as scoring it in the middle.
        self.assertNotEqual(without, with_mid)

    def test_a_story_the_press_already_ran_scores_below_an_open_one(self):
        s = study(the_study="A randomized trial of 5,000 adults")
        open_story = scoring.score_study(s, "2026-09-05", coverage_state="unreported")
        taken = scoring.score_study(s, "2026-09-05", coverage_state="widely_reported")
        self.assertGreater(open_story["score"], taken["score"])


class BandTests(unittest.TestCase):
    def test_bands_are_ordered_and_cover_the_whole_range(self):
        self.assertEqual(scoring.score_band(100), "Lead")
        self.assertEqual(scoring.score_band(0), "Background")
        seen = [scoring.score_band(v) for v in range(0, 101)]
        self.assertEqual(len(set(seen)), 4)

    def test_a_study_cannot_be_a_lead_when_nobody_checked_coverage(self):
        """story_score drops an unmeasured component from both halves of the
        fraction, so a study can reach 100 on everything except the heaviest
        question nobody asked. Two studies in the archive did. The number stays
        as measured; the band does not claim more than the evidence supports."""
        components = {"evidence_type": 5, "journal_tier": 5, "recency": 5,
                      "sample_size": 5, "coverage_gap": None, "accuracy": None}
        score = scoring.story_score(components)
        self.assertEqual(score, 100)
        self.assertEqual(scoring.score_band(score), "Lead")
        self.assertEqual(
            scoring.cap_band(scoring.score_band(score),
                             scoring.UNCHECKED_COVERAGE_CEILING),
            "Strong")

    def test_the_ceiling_only_applies_when_coverage_is_unmeasured(self):
        s = study(the_study="A randomized trial of 5,000 adults",
                  journal="The New England Journal of Medicine",
                  published="September 2026")
        checked = scoring.score_study(s, "2026-09-05", coverage_state="unreported",
                                      verdict="✅ accurate")
        unchecked = scoring.score_study(s, "2026-09-05", coverage_state=None,
                                        verdict="✅ accurate")
        self.assertEqual(checked["band"], "Lead")
        self.assertNotEqual(unchecked["band"], "Lead")

    def test_capping_never_promotes(self):
        for band in scoring.BAND_ORDER:
            capped = scoring.cap_band(band, "Strong")
            self.assertGreaterEqual(scoring.BAND_ORDER.index(capped),
                                    scoring.BAND_ORDER.index(band))

    def test_a_score_is_always_in_range(self):
        for state in (None, "unreported", "lightly_reported", "widely_reported"):
            result = scoring.score_study(study(), "2026-09-05", coverage_state=state)
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)


class ScoreStudyTests(unittest.TestCase):
    def test_the_components_are_kept_so_a_score_can_be_argued_with(self):
        result = scoring.score_study(
            study(the_study="A randomized trial of 4,000 adults"),
            run_date="2026-09-05", coverage_state="unreported", verdict="✅ Accurate",
        )
        self.assertEqual(set(result["components"]), set(scoring.WEIGHTS))
        self.assertEqual(result["evidence_type"], "randomized trial")
        self.assertEqual(result["sample_size"], 4000)
        self.assertEqual(result["journal_tier"], 1)

    def test_a_failed_fact_check_lowers_the_score(self):
        s = study(the_study="A randomized trial of 4,000 adults")
        clean = scoring.score_study(s, "2026-09-05", verdict="✅ Accurate")
        broken = scoring.score_study(s, "2026-09-05", verdict="❌ Major issues")
        self.assertGreater(clean["score"], broken["score"])

    def test_scoring_the_same_study_twice_gives_the_same_answer(self):
        s = study(the_study="Researchers followed 900 adults over 6 years")
        first = scoring.score_study(s, "2026-09-05", coverage_state="unreported")
        second = scoring.score_study(s, "2026-09-05", coverage_state="unreported")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
