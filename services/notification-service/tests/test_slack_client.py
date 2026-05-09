"""Tests for SlackClient (webhook + bot-token paths)."""

import pytest
import respx
from httpx import Response

from app.channels.slack_client import SlackClient
from app.channels.base import ChannelResult


@pytest.mark.asyncio
@respx.mock
async def test_bot_token_calls_chat_postmessage(monkeypatch):
    monkeypatch.setattr("app.channels.slack_client.config.slack_enabled", True)
    monkeypatch.setattr(
        "app.channels.slack_client.config.slack_bot_token", "xoxb-test-token"
    )
    monkeypatch.setattr("app.channels.slack_client.config.slack_webhook_url", "")
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True, "ts": "1.2"})
    )

    client = SlackClient()
    result = await client.send("hello", title="t", metadata={"channel": "#bimo-trades"})

    assert isinstance(result, ChannelResult)
    assert result.success is True
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer xoxb-test-token"
    body = sent.read().decode()
    assert '"channel":"#bimo-trades"' in body or '"channel": "#bimo-trades"' in body


@pytest.mark.asyncio
@respx.mock
async def test_webhook_fallback_when_no_bot_token(monkeypatch):
    monkeypatch.setattr("app.channels.slack_client.config.slack_enabled", True)
    monkeypatch.setattr("app.channels.slack_client.config.slack_bot_token", "")
    monkeypatch.setattr(
        "app.channels.slack_client.config.slack_webhook_url",
        "https://hooks.slack.com/services/T/B/X",
    )
    route = respx.post("https://hooks.slack.com/services/T/B/X").mock(
        return_value=Response(200, text="ok")
    )

    client = SlackClient()
    result = await client.send("hello")

    assert result.success is True
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_bot_token_invalid_auth_returns_failure(monkeypatch):
    monkeypatch.setattr("app.channels.slack_client.config.slack_enabled", True)
    monkeypatch.setattr("app.channels.slack_client.config.slack_bot_token", "xoxb-bad")
    monkeypatch.setattr("app.channels.slack_client.config.slack_webhook_url", "")
    respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": False, "error": "invalid_auth"})
    )

    client = SlackClient()
    result = await client.send("hello")

    assert result.success is False
    assert "invalid_auth" in (result.error_message or "")


@pytest.mark.asyncio
async def test_disabled_returns_failure(monkeypatch):
    monkeypatch.setattr("app.channels.slack_client.config.slack_enabled", False)
    monkeypatch.setattr("app.channels.slack_client.config.slack_bot_token", "")
    monkeypatch.setattr("app.channels.slack_client.config.slack_webhook_url", "")

    client = SlackClient()
    result = await client.send("hello")

    assert result.success is False
