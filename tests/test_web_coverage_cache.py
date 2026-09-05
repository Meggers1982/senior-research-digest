"""The coverage check is the pipeline's only metered dependency.

Its SerpAPI quota is shared with agingwire-research-intelligence and
trending-content, and the digest's PubMed window is 90 days wide while runs are
daily — so the same study comes round many times. These tests pin the cache and
the budget without touching the network.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import web_coverage as wc  # noqa: E402

DIGEST = """
### 1. Grip Strength Predicts Fracture Risk
**Journal:** *Age and Ageing* | **Published:** May 2026
**PMID:** 40000001 | **DOI:** 10.1/a

**The study:** ...

### 2. Sleep Trajectories and Dementia Onset
**Journal:** *Sleep* | **Published:** May 2026
**PMID:** 40000002 | **DOI:** 10.1/b

**The study:** ...
"""


def _result(state="unreported", outlets=()):
    return {"query": "q", "returned": 3, "outlets": list(outlets),
            "articles": [], "state": state}


class DigestParsingTests(unittest.TestCase):
    def test_studies_carry_their_pmid(self):
        self.assertEqual(
            wc.studies_from_digest(DIGEST),
            [("40000001", "Grip Strength Predicts Fracture Risk"),
             ("40000002", "Sleep Trajectories and Dementia Onset")],
        )

    def test_titles_only_helper_still_works(self):
        self.assertEqual(len(wc.titles_from_digest(DIGEST)), 2)

    def test_a_study_with_no_pmid_still_parses(self):
        self.assertEqual(
            wc.studies_from_digest("### 1. Some Headline\n\n**The study:** x"),
            [("", "Some Headline")],
        )


class CoverageBudgetTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Pacing is real in production and pure latency in tests.
        patcher = mock.patch.object(wc, "PAUSE_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_study_is_checked_not_just_the_first_few(self):
        studies = [(str(9000000 + i), f"Study number {i} about falls") for i in range(20)]
        with mock.patch.object(wc, "check_study", return_value=_result()) as check:
            out = wc.check_digest(studies, cache_path=None)
        self.assertEqual(check.call_count, 20)
        self.assertEqual(out["checked"], 20)

    def test_a_runaway_digest_cannot_drain_the_shared_quota(self):
        studies = [(str(9100000 + i), f"Study {i}") for i in range(60)]
        with mock.patch.object(wc, "check_study", return_value=_result()) as check:
            out = wc.check_digest(studies, cache_path=None, limit=5)
        self.assertEqual(check.call_count, 5)
        self.assertEqual(out["checked"], 5)
        self.assertEqual(out["skipped"], 55)

    def test_a_failed_lookup_is_reported_as_skipped_not_as_clean(self):
        """Returning nothing must not read as "no coverage found"."""
        with mock.patch.object(wc, "check_study", return_value=None):
            out = wc.check_digest([("40000001", "A study")], cache_path=None)
        self.assertEqual(out["checked"], 0)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["by_pmid"], {})

    def test_results_are_keyed_by_pmid_so_they_can_reach_the_study_record(self):
        with mock.patch.object(wc, "check_study",
                               return_value=_result("widely_reported", ["AARP"])):
            out = wc.check_digest(wc.studies_from_digest(DIGEST), cache_path=None)
        self.assertEqual(set(out["by_pmid"]), {"40000001", "40000002"})
        self.assertEqual(out["by_pmid"]["40000001"]["state"], "widely_reported")
        self.assertEqual(out["outlets"], {"AARP"})

    def test_no_api_key_skips_without_pretending_the_studies_are_clean(self):
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            out = wc.check_digest(wc.studies_from_digest(DIGEST), cache_path=None)
        self.assertTrue(out["skipped_reason"])
        self.assertEqual(out["by_pmid"], {})


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        patcher = mock.patch.object(wc, "PAUSE_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "coverage_cache.json"

    def test_a_second_run_over_the_same_studies_costs_nothing(self):
        studies = wc.studies_from_digest(DIGEST)
        with mock.patch.object(wc, "check_study", return_value=_result()) as check:
            wc.check_digest(studies, cache_path=self.cache)
            self.assertEqual(check.call_count, 2)
            second = wc.check_digest(studies, cache_path=self.cache)
        self.assertEqual(check.call_count, 2)  # no further lookups
        self.assertEqual(second["cached"], 2)
        self.assertEqual(second["checked"], 0)
        self.assertEqual(set(second["by_pmid"]), {"40000001", "40000002"})

    def test_a_stale_entry_is_rechecked(self):
        old = (datetime.now(timezone.utc)
               - timedelta(days=wc.CACHE_TTL_DAYS + 1)).isoformat()
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps({"studies": {
            "40000001": {"checked_at": old, "result": _result()}
        }}), encoding="utf-8")
        with mock.patch.object(wc, "check_study", return_value=_result()) as check:
            out = wc.check_digest([("40000001", "Grip Strength")], cache_path=self.cache)
        self.assertEqual(check.call_count, 1)
        self.assertEqual(out["cached"], 0)

    def test_a_corrupt_cache_is_ignored_rather_than_fatal(self):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text("{not json", encoding="utf-8")
        with mock.patch.object(wc, "check_study", return_value=_result()):
            out = wc.check_digest([("40000001", "Grip Strength")], cache_path=self.cache)
        self.assertEqual(out["checked"], 1)

    def test_studies_with_no_pmid_are_not_cached(self):
        """There is no stable key for them, so caching would collide by title."""
        with mock.patch.object(wc, "check_study", return_value=_result()):
            wc.check_digest([("", "Untitled study")], cache_path=self.cache)
        self.assertFalse(self.cache.exists())


class RecencyTests(unittest.TestCase):
    def test_the_window_follows_the_config_rather_than_a_hardcoded_literal(self):
        with mock.patch.object(wc, "_serp", return_value={"news_results": []}) as serp:
            wc.check_study("Grip strength predicts fracture", days_back=30)
        self.assertIn("when:30d", serp.call_args[0][0]["q"])


if __name__ == "__main__":
    unittest.main()
