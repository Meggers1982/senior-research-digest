"""Reading the response is the part of the Claude call that can silently lie.

Under adaptive thinking the first content block is a thinking block, so the
`response.content[0].text` this pipeline used on Opus 4.5 would return reasoning
instead of the answer. Nothing about that failure is loud: the digest would just
be wrong. These tests pin the block-selection behaviour with fakes, so they run
without an API key.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import llm  # noqa: E402


class Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class Response:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeClient:
    """Returns the queued responses in order and records each request."""

    def __init__(self, *responses):
        self._queue = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._queue.pop(0)


class TextExtractionTests(unittest.TestCase):
    def test_thinking_blocks_are_not_mistaken_for_the_answer(self):
        response = Response([
            Block("thinking", "Let me weigh the two cohort studies..."),
            Block("text", "# Senior Living Research Digest"),
        ])
        self.assertEqual(llm.text_of(response), "# Senior Living Research Digest")

    def test_the_old_indexing_would_have_returned_the_wrong_block(self):
        """Guards the exact regression: content[0] is no longer the answer."""
        response = Response([Block("thinking", "reasoning"), Block("text", "answer")])
        self.assertEqual(response.content[0].text, "reasoning")
        self.assertEqual(llm.text_of(response), "answer")

    def test_several_text_blocks_are_joined(self):
        response = Response([Block("text", "one "), Block("text", "two")])
        self.assertEqual(llm.text_of(response), "one two")

    def test_no_content_is_an_empty_string_not_a_crash(self):
        self.assertEqual(llm.text_of(Response([])), "")
        self.assertEqual(llm.text_of(Response(None)), "")


class RefusalTests(unittest.TestCase):
    def test_a_refusal_raises_rather_than_returning_empty_text(self):
        client = FakeClient(Response([], stop_reason="refusal"))
        with self.assertRaises(llm.ModelDeclined):
            llm.complete_prose(
                client, system="s", messages=[], continuation_prompt="go", label="x"
            )


class ContinuationTests(unittest.TestCase):
    def test_a_truncated_response_is_continued_and_concatenated(self):
        client = FakeClient(
            Response([Block("text", "first half ")], stop_reason="max_tokens"),
            Response([Block("text", "second half")]),
        )
        messages = [{"role": "user", "content": "write it"}]
        body = llm.complete_prose(
            client, system="s", messages=messages,
            continuation_prompt="continue", label="digest",
        )
        self.assertEqual(body, "first half second half")

    def test_only_this_turns_chunk_is_echoed_back(self):
        """Echoing the accumulated body would duplicate content in the history."""
        client = FakeClient(
            Response([Block("text", "A")], stop_reason="max_tokens"),
            Response([Block("text", "B")], stop_reason="max_tokens"),
            Response([Block("text", "C")]),
        )
        messages = [{"role": "user", "content": "go"}]
        llm.complete_prose(
            client, system="s", messages=messages,
            continuation_prompt="continue", label="digest",
        )
        echoed = [m["content"] for m in messages if m["role"] == "assistant"]
        self.assertEqual(echoed, ["A", "B"])

    def test_continuations_are_capped(self):
        client = FakeClient(*[
            Response([Block("text", "x")], stop_reason="max_tokens") for _ in range(9)
        ])
        llm.complete_prose(
            client, system="s", messages=[], continuation_prompt="c",
            label="digest", max_continuations=2,
        )
        self.assertEqual(len(client.calls), 3)  # the first call plus two retries

    def test_adaptive_thinking_is_requested_on_every_turn(self):
        client = FakeClient(
            Response([Block("text", "a")], stop_reason="max_tokens"),
            Response([Block("text", "b")]),
        )
        llm.complete_prose(
            client, system="s", messages=[], continuation_prompt="c", label="d"
        )
        for call in client.calls:
            self.assertEqual(call["thinking"], {"type": "adaptive"})
            self.assertEqual(call["model"], llm.MODEL)


class JsonTests(unittest.TestCase):
    SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}}

    def test_a_schema_is_passed_as_output_config(self):
        client = FakeClient(Response([Block("text", '{"n": 1}')]))
        result = llm.complete_json(
            client, system="s", messages=[], schema=self.SCHEMA, label="x"
        )
        self.assertEqual(result, {"n": 1})
        self.assertEqual(
            client.calls[0]["output_config"],
            {"format": {"type": "json_schema", "schema": self.SCHEMA}},
        )

    def test_truncated_json_raises_instead_of_being_stitched(self):
        """Prose can be concatenated across turns; a half-written object cannot."""
        client = FakeClient(Response([Block("text", '{"n": ')], stop_reason="max_tokens"))
        with self.assertRaises(ValueError):
            llm.complete_json(
                client, system="s", messages=[], schema=self.SCHEMA, label="digest"
            )


if __name__ == "__main__":
    unittest.main()
