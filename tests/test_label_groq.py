"""Labeller tests with a fake Groq: no network, no tokens spent."""
import json

import pytest

import src.label.label_groq as lg
from tests.test_schema import valid_posting


class FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self.ok = status_code == 200
        self._body = body
        self.text = json.dumps(body)
        self.headers = {"x-ratelimit-remaining-tokens": "8000", **(headers or {})}

    def json(self):
        return self._body


class FakeSession:
    """Returns the queued responses in order and remembers what was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []

    def post(self, url, json, timeout):
        self.sent.append(json)
        item = self.responses.pop(0)
        if isinstance(item, Exception):  # simulate a network failure
            raise item
        return item


def answer(content):
    return FakeResponse(200, {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 2000, "completion_tokens": 300,
                  "completion_tokens_details": {"reasoning_tokens": 100}},
    })


POSTING = {"id": "greenhouse:acme:1", "split": "train", "text": "Data Intern at Acme"}


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    monkeypatch.setattr(lg.time, "sleep", lambda seconds: None)


def test_valid_answer_is_accepted_first_try():
    session = FakeSession([answer(json.dumps(valid_posting()))])
    result = lg.label_one(session, "some-model", POSTING)
    assert result["valid"] and result["attempts"] == 1
    assert result["usage"] == {"prompt_tokens": 2000, "completion_tokens": 300, "reasoning_tokens": 100}


def test_invalid_answer_gets_one_retry_with_the_error():
    bad = json.dumps(valid_posting(work_mode="WFH"))
    session = FakeSession([answer(bad), answer(json.dumps(valid_posting()))])
    result = lg.label_one(session, "some-model", POSTING)
    assert result["valid"] and result["attempts"] == 2
    retry_messages = session.sent[1]["messages"]
    assert "invalid" in retry_messages[-1]["content"]  # the model was told what went wrong


def test_gives_up_after_two_bad_answers():
    session = FakeSession([answer("not json"), answer("still not json")])
    result = lg.label_one(session, "some-model", POSTING)
    assert not result["valid"] and result["label"] is None and result["error"]


def test_thinking_tags_are_removed_before_parsing():
    content = "<think>the company is Acme...</think>" + json.dumps(valid_posting())
    result = lg.label_one(FakeSession([answer(content)]), "some-model", POSTING)
    assert result["valid"]


def test_daily_limit_stops_the_run():
    limit = FakeResponse(429, {"error": {"message": "Rate limit reached on tokens per day (TPD)"}})
    with pytest.raises(lg.DailyLimitReached):
        lg.call_groq(FakeSession([limit]), "some-model", [])


def test_per_minute_limit_waits_and_retries():
    limit = FakeResponse(429, {"error": {"message": "tokens per minute (TPM)"}}, {"retry-after": "3"})
    session = FakeSession([limit, answer("{}")])
    assert lg.call_groq(session, "some-model", []).ok
    assert len(session.sent) == 2


def test_intercepted_network_stops_with_advice():
    session = FakeSession([lg.requests.exceptions.SSLError("self-signed certificate in certificate chain")])
    with pytest.raises(lg.NetworkProblem, match="Switch networks"):
        lg.call_groq(session, "some-model", [])
    assert len(session.sent) == 1  # no pointless retries


def test_dropped_connection_is_retried():
    session = FakeSession([lg.requests.exceptions.ConnectionError("reset"), answer("{}")])
    assert lg.call_groq(session, "some-model", []).ok
    assert len(session.sent) == 2


def test_api_time_excludes_our_waiting():
    result = lg.label_one(FakeSession([answer(json.dumps(valid_posting()))]), "some-model", POSTING)
    assert result["api_seconds"] < 1


@pytest.mark.parametrize("text, seconds", [("615ms", 0.615), ("6s", 6), ("1m26.4s", 86.4), (None, 0)])
def test_parse_duration(text, seconds):
    assert lg.parse_duration(text) == pytest.approx(seconds)


def test_label_goes_stale_when_text_or_guide_changes(tmp_path):
    result = lg.label_one(FakeSession([answer(json.dumps(valid_posting()))]), "some-model", POSTING)
    out = tmp_path / "labels.jsonl"
    out.write_text(json.dumps(result) + "\n")
    current = (result["text_sha1"], result["prompt_sha1"])
    assert lg.up_to_date(out, {POSTING["id"]: current}) == {POSTING["id"]}
    assert lg.up_to_date(out, {POSTING["id"]: ("new-text", current[1])}) == set()
    assert lg.up_to_date(out, {POSTING["id"]: (current[0], "new-guide")}) == set()


def fake_selected():
    rows = []
    for k in range(200):
        rows.append({"id": f"p{k:03}", "split": "train" if k < 150 else "test",
                     "is_intern": k % 10 == 0, "is_india": k % 7 == 0})
    return rows


def test_pilot_uses_train_only_and_is_repeatable():
    first = lg.pick_pilot(fake_selected(), 20)
    assert len(first) == 20
    assert all(p["split"] == "train" for p in first)
    assert [p["id"] for p in first] == [p["id"] for p in lg.pick_pilot(fake_selected(), 20)]
    assert sum(p["is_intern"] for p in first) >= 5
