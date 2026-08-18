import json

import pytest

from app import ai_client


def test_chat_json_parses_clean_json(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **kw: '{"keywords": ["Python"]}')
    assert ai_client.chat_json([{"role": "user", "content": "x"}]) == {"keywords": ["Python"]}


def test_chat_json_strips_code_fences(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **kw: '```json\n{"a": 1}\n```')
    assert ai_client.chat_json([{"role": "user", "content": "x"}]) == {"a": 1}


def test_chat_json_retries_with_bigger_budget_on_truncation(monkeypatch):
    """Regression test: a JD long enough to truncate the model's JSON response used
    to crash /analyze with an unhandled JSONDecodeError. chat_json should retry with
    a larger token budget instead of failing on the first truncated response."""
    calls = []

    def fake_chat(messages, temperature=0.2, max_tokens=1024):
        calls.append(max_tokens)
        if len(calls) == 1:
            return '{"keywords": ["Python", "Doc'  # truncated mid-string
        return '{"keywords": ["Python", "Docker"]}'

    monkeypatch.setattr(ai_client, "chat", fake_chat)
    result = ai_client.chat_json([{"role": "user", "content": "x"}], max_tokens=100)

    assert result == {"keywords": ["Python", "Docker"]}
    assert len(calls) == 2
    assert calls[1] > calls[0]  # budget grew on retry


def test_chat_json_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **kw: '{"keywords": ["truncated')
    with pytest.raises(json.JSONDecodeError):
        ai_client.chat_json([{"role": "user", "content": "x"}], max_attempts=2)
