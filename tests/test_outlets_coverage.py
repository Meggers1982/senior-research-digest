import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import outlets  # noqa: E402
import web_coverage as wc  # noqa: E402


class ClinicalMatchingTests(unittest.TestCase):
    """This digest's topics are clinical; outlet coverage blurbs are not.

    No consumer publication lists "sarcopenia" in what it covers, so a direct
    term match returns nothing and every run falls back to the same generalists.
    """

    def test_a_clinical_topic_returns_suggestions(self):
        for focus in ("osteoporosis", "sarcopenia", "polypharmacy", "vision loss"):
            self.assertTrue(outlets.suggest(focus, "b2c"), focus)

    def test_a_specialist_outranks_a_generalist_on_its_own_subject(self):
        names = [r["publisher"] for r in outlets.suggest("dementia", "b2c", limit=4)]
        self.assertTrue(
            any("dementia" in r["coverage"].lower() or "alzheim" in r["coverage"].lower()
                for r in outlets.suggest("dementia", "b2c", limit=4)),
            names,
        )

    def test_an_empty_focus_still_returns_strong_titles(self):
        rows = outlets.suggest("", "b2c", limit=3)
        self.assertTrue(rows)
        for r in rows:
            self.assertGreaterEqual(r["data_fit"], 4)

    def test_consumer_and_trade_draw_from_their_own_registries(self):
        """A few titles are in both registries on purpose — Next Avenue, USAging
        and the National Council on Aging serve both audiences — so the lists
        overlap rather than being disjoint."""
        consumer = outlets.suggest("falls", "b2c", limit=5)
        trade = outlets.suggest("falls", "b2b", limit=5)
        self.assertTrue(consumer and trade)
        self.assertTrue(all(r["audience"] == "b2c" for r in consumer))
        self.assertTrue(all(r["audience"] == "b2b" for r in trade))
        self.assertNotEqual({r["publisher"] for r in consumer},
                            {r["publisher"] for r in trade})

    def test_excluded_outlets_are_dropped(self):
        first = outlets.suggest("dementia", "b2c", limit=1)[0]["publisher"]
        again = outlets.suggest("dementia", "b2c", limit=1, exclude={first})
        self.assertNotEqual(again[0]["publisher"], first)

    def test_candidate_block_names_the_excluded(self):
        block = outlets.candidate_block("dementia", exclude={"Next Avenue"})
        self.assertIn("do not suggest", block)
        self.assertIn("Next Avenue", block)

    def test_candidate_block_has_both_audiences(self):
        block = outlets.candidate_block("falls")
        self.assertIn("Consumer:", block)
        self.assertIn("Trade:", block)


class CoverageGateTests(unittest.TestCase):
    TITLE = "Simple Grip-Strength Test May Predict Future Osteoporosis Risk in Older Adults"

    def test_a_restatement_of_the_study_matches(self):
        self.assertTrue(wc.title_similar(
            self.TITLE, "Grip strength test predicts osteoporosis risk, study finds"))

    def test_a_topically_related_headline_does_not(self):
        """Google ranks on topic, so the gate is what makes the answer mean anything."""
        self.assertFalse(wc.title_similar(
            self.TITLE, "The best grip strengtheners for climbers in 2026"))

    def test_query_drops_stopwords_and_caps_length(self):
        q = wc.build_query(self.TITLE)
        self.assertNotIn("may", q.lower().split())
        self.assertLessEqual(len(q.split()), wc.MAX_QUERY_WORDS)

    def test_titles_are_read_from_the_digest_markdown(self):
        md = "### 1. First Study Headline\ntext\n### 2. Second Study Headline\n#### not a study\n"
        self.assertEqual(wc.titles_from_digest(md),
                         ["First Study Headline", "Second Study Headline"])

    def test_missing_key_skips_with_a_reason(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}, clear=False):
            result = wc.check_digest([self.TITLE])
        self.assertEqual(result["checked"], 0)
        self.assertIn("SERPAPI_API_KEY", result["skipped_reason"])
        self.assertEqual(result["outlets"], set())


if __name__ == "__main__":
    unittest.main()


class SpecificityTests(unittest.TestCase):
    """Nearly every publication in both registries covers "health" and "aging".

    A topic whose term list was made only of those put every outlet in the top
    band, so the suggestion degraded to "any generalist" for every clinical run.
    The top band now needs a topic-specific hit.
    """

    def test_a_topical_specialist_beats_a_generalist(self):
        cases = {
            ("dementia", "b2c"): "Being Patient",
            ("palliative care", "b2b"): "Hospice News",
            ("nutrition", "b2b"): "Food Management",
        }
        for (focus, audience), expected in cases.items():
            names = [r["publisher"] for r in outlets.suggest(focus, audience, limit=3)]
            self.assertIn(expected, names, f"{focus}/{audience}: {names}")

    def test_different_topics_do_not_return_the_same_list(self):
        """The symptom the split was meant to cure."""
        seen = {}
        for focus in ("dementia", "nutrition", "palliative care", "osteoporosis"):
            seen[focus] = tuple(r["publisher"] for r in outlets.suggest(focus, "b2c", limit=3))
        self.assertEqual(len(set(seen.values())), len(seen), seen)

    def test_every_rotation_topic_has_a_term_mapping(self):
        """An unmapped topic silently falls back to its own words plus
        generalists, which is exactly the behaviour this class exists to stop."""
        config = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "digest_config.json")
            .read_text(encoding="utf-8")
        )
        for topic in config["focus_rotation"]:
            if not topic:
                continue
            self.assertIn(topic, outlets.TOPIC_TERMS, topic)

    def test_every_mapping_has_both_kinds_of_term(self):
        for topic, terms in outlets.TOPIC_TERMS.items():
            self.assertTrue(terms.get("specific"), topic)
            self.assertTrue(terms.get("general"), topic)

    def test_a_specific_term_is_not_secretly_a_general_one(self):
        generic = {"health", "aging", "wellness", "senior"}
        for topic, terms in outlets.TOPIC_TERMS.items():
            self.assertEqual(set(terms["specific"]) & generic, set(), topic)


class TermLookupTests(unittest.TestCase):
    def test_a_focus_matches_its_own_key(self):
        self.assertEqual(
            outlets._terms_for("palliative care"), outlets.TOPIC_TERMS["palliative care"])

    def test_matching_is_on_whole_words_not_raw_substrings(self):
        """`key in focus or focus in key` matched fragments; a focus of "care"
        should not silently become "palliative care"."""
        self.assertNotEqual(
            outlets._terms_for("care"), outlets.TOPIC_TERMS["palliative care"])

    def test_an_unmapped_focus_still_gets_its_own_words_as_specific(self):
        terms = outlets._terms_for("hydration")
        self.assertIn("hydration", terms["specific"])

    def test_an_empty_focus_has_no_specific_terms(self):
        self.assertEqual(outlets._terms_for("")["specific"], [])


class RegistryFailureTests(unittest.TestCase):
    def test_a_missing_registry_fails_loudly(self):
        """It used to return (), so a renamed CSV produced a run with no pitch
        targets, no error, and nothing to notice."""
        with self.assertRaises(RuntimeError):
            outlets._load("/nonexistent/publications.csv", "b2c")
