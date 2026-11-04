"""Temporary model errors are retried. Permanent ones fail at once."""
import httpx
import pytest

from app.core.errors import PipelineError
from app.pipeline import llm


def script(monkeypatch, *outcomes):
    calls, waits = [], []

    def fake_post(*args, **kwargs):
        calls.append(args)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"ok": True})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    return calls, waits


def post():
    return llm._post("http://model.test", "key", {})


def test_temporary_error_is_retried_until_it_works(monkeypatch):
    calls, waits = script(monkeypatch, 503, 429, 200)
    assert post() == {"ok": True}
    assert len(calls) == 3 and waits == [2, 5]


def test_network_error_is_retried(monkeypatch):
    calls, _ = script(monkeypatch, httpx.ConnectError("down"), 200)
    assert post() == {"ok": True}
    assert len(calls) == 2


def test_permanent_error_fails_without_retrying(monkeypatch):
    calls, waits = script(monkeypatch, 401)
    with pytest.raises(PipelineError) as e:
        post()
    assert e.value.error_class == "llm_http_error"
    assert len(calls) == 1 and waits == []


@pytest.mark.parametrize("status,error_class", [(503, "llm_http_error"), (429, "llm_rate_limited")])
def test_gives_up_after_the_last_retry(monkeypatch, status, error_class):
    calls, waits = script(monkeypatch, status, status, status, status)
    with pytest.raises(PipelineError) as e:
        post()
    assert e.value.error_class == error_class
    assert len(calls) == 4 and waits == [2, 5, 12]


def test_network_error_after_the_last_retry_is_unreachable(monkeypatch):
    down = httpx.ConnectError("down")
    script(monkeypatch, down, down, down, down)
    with pytest.raises(PipelineError) as e:
        post()
    assert e.value.error_class == "llm_unreachable"
