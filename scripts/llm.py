"""One place where this pipeline talks to Claude.

`digest_generator`, `fact_checker` and `trends` each grew their own copy of the
same call — model string, cache breakpoints, and a continuation loop for when a
response hits `max_tokens`. Two of the three copies drifted: `trends` never got
the retry and never got prompt caching, despite sending the largest payload of
the three (a whole new digest plus a whole previous one plus the topic memory).

Reading the response is the part that has to be right. Under adaptive thinking
the first content block is a *thinking* block, so the old `response.content[0].text`
would have returned the wrong thing — or raised — the moment the model changed.
`text_of` walks the blocks instead.
"""
from __future__ import annotations

MODEL = "claude-opus-5"

# Non-streaming ceiling. The SDK wants streaming past this, and no call here
# needs a longer single turn than the continuation loop already provides.
MAX_TOKENS = 16000

MAX_CONTINUATIONS = 3


class ModelDeclined(RuntimeError):
    """The model returned `stop_reason: "refusal"`.

    Raised rather than returned so a caller can't mistake an empty string for
    ordinary output. Callers that have a deterministic fallback should catch it.
    """


def text_of(response) -> str:
    """Concatenate the response's text blocks.

    Adaptive thinking is on, so `content` opens with a thinking block whose
    `.text` is not the answer. Selecting by type is the only safe read.
    """
    return "".join(
        block.text
        for block in (response.content or [])
        if getattr(block, "type", None) == "text"
    )


def _create(client, *, system, messages, max_tokens, model, output_schema=None):
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "thinking": {"type": "adaptive"},
    }
    if output_schema is not None:
        kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": output_schema}
        }
    response = client.messages.create(**kwargs)
    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        raise ModelDeclined(getattr(details, "category", None) or "unspecified")
    return response


def complete_prose(
    client,
    *,
    system,
    messages,
    continuation_prompt: str,
    label: str,
    max_tokens: int = MAX_TOKENS,
    model: str = MODEL,
    max_continuations: int = MAX_CONTINUATIONS,
) -> str:
    """Run a prose call, continuing it if the response hits the token ceiling.

    `messages` is mutated with the turns that actually happened, which is what
    the model needs to see to pick up where it stopped. Only this turn's partial
    text is echoed back, not the accumulated body, so history doesn't duplicate.
    """
    response = _create(
        client, system=system, messages=messages,
        max_tokens=max_tokens, model=model,
    )
    chunk = text_of(response)
    body = chunk

    continuations = 0
    while response.stop_reason == "max_tokens" and continuations < max_continuations:
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": continuation_prompt})
        response = _create(
            client, system=system, messages=messages,
            max_tokens=max_tokens, model=model,
        )
        chunk = text_of(response)
        body += chunk
        continuations += 1

    if response.stop_reason == "max_tokens":
        print(
            f"  WARNING: {label} still truncated after {max_continuations} "
            "continuation(s) — output may be incomplete."
        )
    return body


def complete_json(
    client,
    *,
    system,
    messages,
    schema: dict,
    label: str,
    max_tokens: int = MAX_TOKENS,
    model: str = MODEL,
):
    """Run a call constrained to `schema` and return the parsed object.

    There is deliberately no continuation loop here. A truncated JSON response
    cannot be repaired by concatenating the next turn's text the way prose can —
    the result is a broken document, not a shorter one. Callers keep responses
    inside one turn by batching their input instead.
    """
    import json

    response = _create(
        client, system=system, messages=messages,
        max_tokens=max_tokens, model=model, output_schema=schema,
    )
    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"{label}: response hit max_tokens, so the JSON is incomplete. "
            "Send fewer items per call."
        )
    return json.loads(text_of(response))


def cached(text: str) -> dict:
    """A text block marked as a prompt-cache breakpoint."""
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
