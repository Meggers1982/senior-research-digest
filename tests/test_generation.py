"""The two Claude-facing steps, driven by fakes so they run without a key.

Both used to ask for markdown and stitch truncated turns back together. They now
ask for records in batches, because a half-written JSON array cannot be repaired
the way half a paragraph can. What matters here is that the batching covers every
input, and that nothing the model invents reaches the digest.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import digest_generator  # noqa: E402
import fact_checker  # noqa: E402


class Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class Response:
    stop_reason = "end_turn"

    def __init__(self, payload):
        self.content = [Block(json.dumps(payload))]


class FakeMessages:
    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responder(kwargs)


class FakeClient:
    def __init__(self, responder):
        self.messages = FakeMessages(responder)


def study(pmid):
    return {field: f"{field} for {pmid}" for field in
            ("headline", "journal", "published", "doi", "the_study",
             "why_it_matters", "story_angle_primary", "story_angle_secondary",
             "caveats")} | {"pmid": pmid}


def pmids_in(kwargs):
    text = kwargs["messages"][0]["content"]
    if isinstance(text, list):
        text = "".join(b["text"] for b in text)
    import re
    return re.findall(r"--- PMID (\d+) ---", text)


class DigestBatchingTests(unittest.TestCase):
    def _run(self, abstracts, responder):
        client = FakeClient(responder)
        with mock.patch.object(digest_generator.anthropic, "Anthropic", return_value=client):
            markdown, selected, records = digest_generator.generate_digest(
                subject_focus="sleep", primary_audience="older adults",
                secondary_audience="families", abstracts=abstracts,
                journal_count=167, api_key="test",
            )
        return client, markdown, selected, records

    def test_every_abstract_reaches_a_batch(self):
        abstracts = {str(40000000 + i): f"abstract {i}" for i in range(30)}
        client, _, _, records = self._run(
            abstracts, lambda kw: Response({"studies": [study(p) for p in pmids_in(kw)]}))
        self.assertEqual(len(client.messages.calls), 3)   # 30 / 12, rounded up
        self.assertEqual(len(records), 30)
        seen = [p for call in client.messages.calls for p in pmids_in(call)]
        self.assertEqual(sorted(seen), sorted(abstracts))

    def test_a_schema_is_sent_on_every_call(self):
        abstracts = {"40000001": "a", "40000002": "b"}
        client, _, _, _ = self._run(
            abstracts, lambda kw: Response({"studies": [study("40000001")]}))
        for call in client.messages.calls:
            self.assertIn("output_config", call)
            self.assertEqual(call["thinking"], {"type": "adaptive"})

    def test_a_pmid_the_model_invented_is_dropped(self):
        """A fabricated citation is worse than a study left out."""
        abstracts = {"40000001": "a"}
        _, markdown, selected, records = self._run(
            abstracts,
            lambda kw: Response({"studies": [study("40000001"), study("99999999")]}))
        self.assertEqual(selected, ["40000001"])
        self.assertEqual(len(records), 1)
        self.assertNotIn("99999999", markdown)

    def test_selecting_fewer_studies_than_abstracts_is_normal(self):
        abstracts = {"40000001": "a", "40000002": "b"}
        _, _, selected, _ = self._run(
            abstracts, lambda kw: Response({"studies": [study("40000001")]}))
        self.assertEqual(selected, ["40000001"])

    def test_a_declined_batch_loses_only_its_own_studies(self):
        abstracts = {str(40000000 + i): "x" for i in range(24)}
        calls = {"n": 0}

        def responder(kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                response = Response({"studies": []})
                response.stop_reason = "refusal"
                response.stop_details = None
                return response
            return Response({"studies": [study(p) for p in pmids_in(kwargs)]})

        _, _, selected, _ = self._run(abstracts, responder)
        self.assertEqual(len(selected), 12)   # the second batch survives

    def test_a_truncated_batch_loses_only_its_own_studies(self):
        """complete_json refuses to stitch half a JSON array and raises
        ValueError. The caller has to survive that the way it survives a
        refusal -- otherwise one oversized batch costs the whole run."""
        abstracts = {str(40000000 + i): "x" for i in range(24)}
        calls = {"n": 0}

        def responder(kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                response = Response({"studies": []})
                response.stop_reason = "max_tokens"
                return response
            return Response({"studies": [study(p) for p in pmids_in(kwargs)]})

        _, _, selected, _ = self._run(abstracts, responder)
        self.assertEqual(len(selected), 12)   # the second batch survives

    def test_an_unparseable_batch_loses_only_its_own_studies(self):
        abstracts = {str(40000000 + i): "x" for i in range(24)}
        calls = {"n": 0}

        def responder(kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                response = Response({"studies": []})
                response.content = [Block("{not json")]
                return response
            return Response({"studies": [study(p) for p in pmids_in(kwargs)]})

        _, _, selected, _ = self._run(abstracts, responder)
        self.assertEqual(len(selected), 12)

    def test_no_abstracts_produces_a_digest_that_says_so(self):
        client = FakeClient(lambda kw: Response({"studies": []}))
        with mock.patch.object(digest_generator.anthropic, "Anthropic", return_value=client):
            markdown, selected, records = digest_generator.generate_digest(
                subject_focus="", primary_audience="a", secondary_audience="b",
                abstracts={}, journal_count=167, api_key="test",
            )
        self.assertEqual((selected, records), ([], []))
        self.assertIn("No articles", markdown)
        self.assertEqual(client.messages.calls, [])


class FactCheckTests(unittest.TestCase):
    def _run(self, pmids, responder):
        client = FakeClient(responder)
        with mock.patch.object(fact_checker.anthropic, "Anthropic", return_value=client), \
             mock.patch.object(fact_checker, "fetch_abstract", side_effect=lambda p, k: f"abstract {p}"):
            report, records = fact_checker.run_fact_check(
                digest_content="**Primary audience:** older adults\n",
                selected_pmids=pmids, ncbi_api_key=None,
                anthropic_api_key="test", subject_focus="sleep",
            )
        return client, report, records

    def _verdict(self, pmid, number=1, verdict="accurate"):
        return {"number": number, "pmid": pmid, "headline": f"study {pmid}",
                "verdict": verdict, "notes": "", "issues": []}

    def test_studies_are_batched(self):
        pmids = [str(40000000 + i) for i in range(25)]
        client, _, records = self._run(
            pmids,
            lambda kw: Response({"studies": [self._verdict(p, i) for i, p in
                                             enumerate(pmids_in(kw), start=1)]}))
        self.assertEqual(len(client.messages.calls), 3)   # 25 / 10, rounded up
        self.assertEqual(len(records), 25)

    def test_a_truncated_batch_leaves_the_other_verdicts_intact(self):
        pmids = [str(40000000 + i) for i in range(20)]
        calls = {"n": 0}

        def responder(kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                response = Response({"studies": []})
                response.stop_reason = "max_tokens"
                return response
            return Response({"studies": [self._verdict(p, i) for i, p in
                                         enumerate(pmids_in(kwargs), start=1)]})

        _, _, records = self._run(pmids, responder)
        self.assertEqual(len(records), 10)   # the second batch survives

    def test_a_verdict_for_an_unknown_pmid_is_discarded(self):
        _, report, records = self._run(
            ["40000001"],
            lambda kw: Response({"studies": [self._verdict("40000001"),
                                             self._verdict("99999999", 2)]}))
        self.assertEqual([r["pmid"] for r in records], ["40000001"])
        self.assertNotIn("99999999", report)

    def test_a_duplicated_verdict_is_kept_once(self):
        _, _, records = self._run(
            ["40000001"],
            lambda kw: Response({"studies": [self._verdict("40000001"),
                                             self._verdict("40000001", 2, "minor")]}))
        self.assertEqual(len(records), 1)

    def test_the_header_counts_what_was_checked_not_what_was_sent(self):
        """The old header reported abstracts supplied; 13 archived reports claim
        40 studies reviewed against roughly 20 verdicts."""
        _, report, _ = self._run(
            ["40000001", "40000002"],
            lambda kw: Response({"studies": [self._verdict("40000001")]}))
        self.assertIn("**Studies reviewed:** 1", report)

    def test_the_report_carries_the_heading_the_parser_expects(self):
        _, report, _ = self._run(
            ["40000001"], lambda kw: Response({"studies": [self._verdict("40000001")]}))
        self.assertIn("### Study 1:", report)
        self.assertIn("**PMID:** 40000001 | **Verdict:**", report)


if __name__ == "__main__":
    unittest.main()
