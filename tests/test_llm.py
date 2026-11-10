import json

import httpx
import pytest

from radio.llm import AnthropicLlm, LlmError, LlmReply, OpenRouterLlm, llm_from_config
from radio.config import Config

KEY = "sk-or-SECRET123"


def make(handler):
    seen = []

    def wrapped(req):
        seen.append(req)
        return handler(req)
    llm = OpenRouterLlm(KEY, client=httpx.Client(transport=httpx.MockTransport(wrapped)))
    return llm, seen


def ok(content="Hola", finish="stop"):
    body = {"choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content}}]}
    return lambda req: httpx.Response(200, json=body)


def test_request_shape():
    llm, seen = make(ok())
    reply = llm.complete("Dime algo", model="anthropic/claude-sonnet-5.5", max_tokens=123)
    assert reply == LlmReply(text="Hola", stop="end")
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(req.content) == {
        "model": "anthropic/claude-sonnet-5.5",
        "messages": [{"role": "user", "content": "Dime algo"}], "max_tokens": 123}


def test_default_timeout_is_180():
    assert OpenRouterLlm(KEY).client.timeout.read == 180.0


@pytest.mark.parametrize("finish,stop", [("stop", "end"), ("length", "max_tokens"),
                                         ("content_filter", "refusal"), ("tool_calls", "other"),
                                         (None, "other")])
def test_finish_reason_mapping(finish, stop):
    llm, _ = make(ok(finish=finish))
    assert llm.complete("p", model="m", max_tokens=1).stop == stop


def test_null_content_gives_empty_text():
    llm, _ = make(ok(content=None))
    assert llm.complete("p", model="m", max_tokens=1).text == ""


def test_list_content_parts_joined():
    parts = [{"type": "text", "text": "Hola "}, {"type": "image"}, {"type": "text", "text": "mundo"}]
    llm, _ = make(ok(content=parts))
    assert llm.complete("p", model="m", max_tokens=1).text == "Hola mundo"


def test_missing_choices_or_message_is_empty_reply():
    llm, _ = make(lambda r: httpx.Response(200, json={"choices": [{"finish_reason": "stop"}]}))
    assert llm.complete("p", model="m", max_tokens=1) == LlmReply(text="", stop="end")
    llm, _ = make(lambda r: httpx.Response(200, json={"choices": []}))
    assert llm.complete("p", model="m", max_tokens=1).text == ""


def test_error_body_with_http_200():
    llm, _ = make(lambda r: httpx.Response(200, json={"error": {"code": 429, "message": "rate limited"}}))
    with pytest.raises(LlmError, match="rate limited") as ei:
        llm.complete("p", model="m", max_tokens=1)
    assert KEY not in str(ei.value)


def test_non_2xx_raises_without_key():
    llm, _ = make(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}},
                                           headers={"x-echo": KEY}))
    with pytest.raises(LlmError, match="401") as ei:
        llm.complete("p", model="m", max_tokens=1)
    assert KEY not in str(ei.value) and KEY not in repr(ei.value)


def test_non_json_body_raises_without_key():
    llm, _ = make(lambda r: httpx.Response(200, text="<html>" + KEY))
    with pytest.raises(LlmError) as ei:
        llm.complete("p", model="m", max_tokens=1)
    assert KEY not in str(ei.value)


def test_error_message_that_echoes_key_is_redacted():
    llm, _ = make(lambda r: httpx.Response(401, json={"error": {"message": f"invalid {KEY}"}}))
    with pytest.raises(LlmError) as ei:
        llm.complete("p", model="m", max_tokens=1)
    assert KEY not in str(ei.value)


def test_transport_error_wrapped_without_key():
    def boom(req):
        raise httpx.ConnectError("down " + KEY)
    llm, _ = make(boom)
    with pytest.raises(LlmError) as ei:
        llm.complete("p", model="m", max_tokens=1)
    assert KEY not in str(ei.value)


def test_anthropic_adapter_maps_sdk_shape():
    from types import SimpleNamespace as NS
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(content=[NS(type="thinking"), NS(text="Hola")], stop_reason="max_tokens")
    llm = AnthropicLlm(NS(messages=NS(create=create)))
    r = llm.complete("p", model="m", max_tokens=9)
    assert r == LlmReply(text="Hola", stop="max_tokens")
    assert calls[0] == {"model": "m", "max_tokens": 9, "messages": [{"role": "user", "content": "p"}]}
    for sdk, ours in [("end_turn", "end"), ("refusal", "refusal"), ("tool_use", "other")]:
        llm = AnthropicLlm(NS(messages=NS(create=lambda **kw: NS(content=[], stop_reason=sdk))))
        assert llm.complete("p", model="m", max_tokens=1) == LlmReply(text="", stop=ours)


def test_llm_from_config_requires_key_and_rejects_unknown(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        llm_from_config(Config(llm_provider="openrouter"))
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    assert isinstance(llm_from_config(Config(llm_provider="openrouter")), OpenRouterLlm)
    with pytest.raises(ValueError, match="foo"):
        llm_from_config(Config(llm_provider="foo"))
