"""Tests for notification-service config."""


def test_slack_channel_performance_default():
    from app.config import config

    assert config.slack_channel_performance == "#bimo-performance"


def test_slack_channel_critical_default():
    from app.config import config

    assert config.slack_channel_critical == "#trading-critical"


def test_slack_channel_alerts_default():
    from app.config import config

    assert config.slack_channel_alerts == "#trading-alerts"
