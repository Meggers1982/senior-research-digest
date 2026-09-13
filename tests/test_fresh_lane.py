"""The new-this-week lane that replaced elderly-geriatric-digest (MEA-573).

None of this touches an API. The live half -- does PubMed accept the qualified
query, how many studies a week produces -- was measured on 2026-09-13 (571
found, 458 screened, 40 selected) and is not something a unit test can hold.
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard_data as bdd  # noqa: E402
import digest_generator  # noqa: E402
import fresh_lane  # noqa: E402
import journals  # noqa: E402
import main  # noqa: E402
import pubmed  # noqa: E402
import web_coverage as wc  # noqa: E402
from test_generation import FakeClient, Response, study, pmids_in  # noqa: E402

ISSN = re.compile(r"^\d{4}-\d{3}[\dX]$")


class JournalGroupTests(unittest.TestCase):
    def test_every_qualified_name_is_on_the_curated_list(self):
        """A typo here would silently search that journal unqualified."""
        names = {name for name, _ in journals.SENIOR_CARE_JOURNALS}
        self.assertEqual(journals.AGE_QUALIFIED_JOURNALS - names, set())

    def test_extended_list_is_well_formed(self):
        rows = journals.extended_journals()
        self.assertEqual(len(rows), 445)
        for row in rows:
            self.assertRegex(row["issn"], ISSN, row["journal"])
            self.assertIn(row["group"], {"aging", "general"})

    def test_no_journal_is_searched_twice_or_in_both_groups(self):
        plain, qualified = journals.new_this_week_issns()
        together = [i.upper() for i in plain + qualified]
        self.assertEqual(len(together), len(set(together)))
        self.assertEqual(len(together), 167 + 445)

    def test_the_rotation_list_is_untouched(self):
        self.assertEqual(len(journals.ISSNS), 167)

    def test_qualifier_leaves_out_bare_aged(self):
        """"aged"[tiab] matches "aged 18 to 45" and would qualify nothing."""
        self.assertNotIn('"aged"[tiab]', journals.OLDER_ADULT_QUALIFIER)
        self.assertEqual(journals.OLDER_ADULT_QUALIFIER.count("("),
                         journals.OLDER_ADULT_QUALIFIER.count(")"))


class FakeHTTP:
    def __init__(self, payloads):
        self.payloads, self.params = list(payloads), []

    def __call__(self, url, params, timeout=30):
        self.params.append(dict(params))
        payload = self.payloads.pop(0)
        return mock.Mock(json=lambda: payload)


class PubMedTests(unittest.TestCase):
    def test_the_qualifier_is_anded_onto_every_batch(self):
        http = FakeHTTP([{"esearchresult": {"idlist": ["1"]}}] * 2)
        with mock.patch.object(pubmed, "_get", http):
            pubmed.search_by_issns(["0000-0001"] * 30, qualifier="(x[tiab])")
        self.assertEqual(len(http.params), 2)
        for params in http.params:
            self.assertTrue(params["term"].endswith(" AND (x[tiab])"), params["term"])

    def test_no_qualifier_leaves_the_term_as_it_was(self):
        http = FakeHTTP([{"esearchresult": {"idlist": []}}])
        with mock.patch.object(pubmed, "_get", http):
            pubmed.search_by_issns(["0000-0001"], subject_focus="sleep")
        self.assertEqual(http.params[0]["term"], '(0000-0001[issn]) AND ("sleep"[Title/Abstract])')

    def test_summaries_are_fetched_in_chunks_and_merged(self):
        http = FakeHTTP([
            {"result": {"uids": ["1", "2"], "1": {"title": "a"}, "2": {"title": "b"}}},
            {"result": {"uids": ["3"], "3": {"title": "c"}}},
        ])
        with mock.patch.object(pubmed, "_get", http):
            merged = pubmed.fetch_summaries(["1", "2", "3"], chunk=2)
        self.assertEqual([p["id"] for p in http.params], ["1,2", "3"])
        self.assertEqual(merged["uids"], ["1", "2", "3"])
        self.assertEqual(merged["3"], {"title": "c"})

    def test_no_pmids_is_no_call(self):
        with mock.patch.object(pubmed, "_get") as get:
            self.assertEqual(pubmed.fetch_summaries([]), {})
        get.assert_not_called()


def summary(title, journal="Some Journal", pubtype=("Journal Article",),
            abstract=True, date="2026/09/10 00:00"):
    return {"title": title, "fulljournalname": journal, "source": journal,
            "pubtype": list(pubtype), "sortpubdate": date,
            "attributes": ["Has Abstract"] if abstract else []}


class ScreenTests(unittest.TestCase):
    def test_each_rule_drops_what_it_should(self):
        summaries = {
            "uids": ["1", "2", "3", "4", "5", "6"],
            "1": summary("Walking and falls in older adults: a cohort study"),
            "2": summary("An editorial on falls", pubtype=("Editorial",)),
            "3": summary("Falls among residents", abstract=False),
            "4": summary("Tau spreading in mice"),
            "5": summary("Already in last week's digest"),
            "6": {"error": "cannot get document summary"},
        }
        kept, dropped = fresh_lane.screen(summaries, exclude={"5"})
        self.assertEqual([c["pmid"] for c in kept], ["1"])
        self.assertEqual(dropped, {"already_written_up": 1, "publication_type": 1,
                                   "no_abstract": 1, "animal_only": 1})

    def test_an_animal_title_that_names_patients_is_kept(self):
        self.assertFalse(fresh_lane.is_animal_only("Patients and a mouse model of frailty"))

    def test_design_journal_and_novelty_outrank_a_plain_title(self):
        summaries = {
            "1": summary("Notes on hearing in later life"),
            "2": summary("First randomized trial of deprescribing in nursing homes", journal="JAMA"),
        }
        kept, _ = fresh_lane.screen(summaries, exclude=set())
        self.assertEqual([c["pmid"] for c in kept], ["2", "1"])

    def test_prior_pmids_reads_digests_not_fact_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "Senior Living Research Digest — Sleep — May 2026.md").write_text(
                "**PMID:** 111 | **DOI:** x\n**PMID:** 222", encoding="utf-8")
            (out / "Senior Living Research Digest — Sleep — May 2026 Fact Check.md").write_text(
                "**PMID:** 333", encoding="utf-8")
            self.assertEqual(fresh_lane.prior_pmids(out), {"111", "222"})


def candidates(n):
    return [{"pmid": str(i), "title": f"title {i}"} for i in range(n)]


class CoverageSelectionTests(unittest.TestCase):
    CFG = {"coverage_checks": 4, "max_abstracts": 3, "coverage_days": 14}

    def test_widely_reported_studies_are_dropped(self):
        result = {"by_pmid": {"0": {"state": "widely_reported"},
                              "1": {"state": "unreported"}}}
        with mock.patch.object(wc, "check_digest", return_value=result) as check:
            selected, coverage = fresh_lane.drop_widely_covered(candidates(10), self.CFG)
        self.assertEqual([c["pmid"] for c in selected], ["1", "2", "3"])
        self.assertEqual(coverage["dropped_widely_reported"], 1)
        self.assertEqual(check.call_args.kwargs["days_back"], 14)
        self.assertEqual(len(check.call_args.args[0]), 4)

    def test_a_short_pool_is_topped_up_from_below(self):
        result = {"by_pmid": {p: {"state": "widely_reported"} for p in "012"}}
        with mock.patch.object(wc, "check_digest", return_value=result):
            selected, _ = fresh_lane.drop_widely_covered(candidates(10), self.CFG)
        self.assertEqual([c["pmid"] for c in selected], ["3", "4", "5"])

    def test_no_serpapi_key_keeps_everything(self):
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            selected, coverage = fresh_lane.drop_widely_covered(candidates(10), self.CFG)
        self.assertEqual(len(selected), 3)
        self.assertIn("skipped_reason", coverage)


class FeedbackTests(unittest.TestCase):
    def fetch(self, url):
        if url.endswith("/api/status"):
            return [
                {"study_id": "elderly-geriatric:100", "status": "saved"},
                {"study_id": "elderly-geriatric:200", "status": "deleted"},
                {"study_id": "senior-research:300", "status": "pitched"},
                {"study_id": "cardiology-heart:400", "status": "saved"},
            ]
        if url.endswith("/elderly-geriatric.json"):
            return {"studies": [{"pmid": "100", "headline": "Liked one"},
                                {"pmid": "200", "headline": "Disliked one"},
                                {"pmid": "400", "headline": "Other beat"}]}
        raise OSError("404")  # senior-research.json before its first sync

    def test_saves_and_passes_become_examples(self):
        note = fresh_lane.feedback_note(fetch=self.fetch)
        self.assertIn("- Liked one", note)
        self.assertIn("- Disliked one", note)
        self.assertNotIn("Other beat", note)

    def test_an_unreachable_dashboard_is_no_note_not_a_crash(self):
        def down(url):
            raise OSError("down")
        self.assertEqual(fresh_lane.feedback_note(fetch=down), "")


class NoResultsTests(unittest.TestCase):
    """SerpAPI reports "no results" as an error body. That is the answer."""

    def _urlopen(self, payload):
        body = io.BytesIO(json.dumps(payload).encode())
        response = mock.MagicMock()
        response.__enter__.return_value = body
        return mock.patch.object(wc.urllib.request, "urlopen", return_value=response)

    def test_no_results_is_unreported_not_skipped(self):
        payload = {"error": "Google News hasn't returned any results for this query."}
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "k"}), self._urlopen(payload):
            result = wc.check_study("Grip strength and mortality in older women")
        self.assertIsNotNone(result)
        self.assertEqual(result["state"], "unreported")

    def test_a_spent_quota_is_still_a_failure(self):
        payload = {"error": "Your account has run out of searches."}
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "k"}), self._urlopen(payload):
            self.assertIsNone(wc.check_study("Grip strength and mortality in older women"))


class NamingTests(unittest.TestCase):
    NOW = datetime(2026, 9, 13)

    def test_the_fresh_lane_files_by_date(self):
        self.assertEqual(main.digest_filename("fresh", "New this week", self.NOW),
                         "Senior Living Research Digest — New This Week — 2026-09-13.md")

    def test_the_topic_lane_is_unchanged(self):
        self.assertEqual(main.digest_filename("topic", "sleep", self.NOW),
                         "Senior Living Research Digest — Sleep — September 2026.md")
        self.assertEqual(main.digest_filename("topic", "", self.NOW),
                         "Senior Living Research Digest — September 2026.md")

    def test_a_twentieth_part_does_not_overwrite_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "Digest.md"
            base.write_text("first")
            for n in range(2, 21):
                (Path(tmp) / f"Digest (Part {n}).md").write_text("x")
            self.assertEqual(main.unique_output_path(base).name, "Digest (Part 21).md")

    def test_an_unknown_lane_stops_the_run(self):
        with mock.patch.dict(os.environ, {"DIGEST_LANE": "weekly"}):
            with self.assertRaises(SystemExit):
                main.pick_lane()


class GeneratorLaneTests(unittest.TestCase):
    def test_header_and_guidance_follow_the_lane(self):
        client = FakeClient(lambda kw: Response({"studies": [study(p) for p in pmids_in(kw)]}))
        with mock.patch.object(digest_generator.anthropic, "Anthropic", return_value=client):
            markdown, _, _ = digest_generator.generate_digest(
                subject_focus="", primary_audience="older adults",
                secondary_audience="families", abstracts={"40000001": "a"},
                journal_count=612, api_key="test", focus_label="New this week",
                days_back=7, guidance="ONLY OLDER ADULTS", screened_note=" (of 571 published)",
            )
        self.assertIn("**Focus:** New this week", markdown)
        self.assertIn("Last 7 days", markdown)
        self.assertIn("**Articles screened:** 1 (of 571 published)", markdown)
        self.assertIn("ONLY OLDER ADULTS", client.messages.calls[0]["messages"][0]["content"])
        self.assertNotIn("Subject focus", client.messages.calls[0]["messages"][0]["content"])


class SharedDashboardTests(unittest.TestCase):
    def run_(self, focus, date, pmids):
        return {"focus": focus, "run_date": date, "primary_audience": "older adults",
                "secondary_audience": "families",
                "studies": [{"pmid": p, "title": f"Headline {p}", "journal": "JAMA",
                             "published": "2026-09-10", "doi": "Not available",
                             "the_study": "did", "why_it_matters": "matters",
                             "story_angle_primary": "you should", "story_angle_secondary": "",
                             "caveats": "small", "score": 74, "band": "Strong",
                             "evidence_type": "rct", "verdict": "✅ Accurate",
                             "coverage_state": "unreported", "covered_by": [],
                             "tags": ["sleep", "falls"]} for p in pmids]}

    def test_only_the_fresh_lane_is_published_and_each_pmid_once(self):
        payload = bdd.shared_dashboard_payload([
            self.run_("New this week", "2026-09-13", ["1", "2"]),
            self.run_("New this week", "2026-09-12", ["2", "3"]),
            self.run_("sleep", "2026-09-13", ["9"]),
        ])
        self.assertEqual(payload["source_id"], "senior-research")
        self.assertEqual([s["pmid"] for s in payload["studies"]], ["1", "2", "3"])
        self.assertEqual(payload["studies"][1]["run_date"], "2026-09-13")
        self.assertEqual(payload["last_updated"], "2026-09-13")

    def test_fields_arrive_in_the_dashboards_shape(self):
        study_ = bdd.shared_dashboard_payload(
            [self.run_("New this week", "2026-09-13", ["1"])])["studies"][0]
        self.assertEqual(study_["relevance_score"], 7)
        self.assertEqual(study_["doi"], "")
        self.assertEqual(study_["fact_check_note"], "")
        self.assertEqual(study_["category"], "Falls")  # first in TAG_TERMS order
        self.assertTrue(study_["media_coverage"].startswith("Not widely covered"))
        self.assertEqual(len(study_["pitch_angles"]), 1)  # the empty trade angle is dropped


if __name__ == "__main__":
    unittest.main()
