"""portfolio_manager_url must not point at the notification-service port."""

from app.config import Settings


def test_portfolio_manager_url_uses_port_8003():
    settings = Settings()
    assert settings.portfolio_manager_url.endswith(":8003"), (
        f"portfolio_manager_url is {settings.portfolio_manager_url}; "
        "8006 is notification-service"
    )


def test_portfolio_manager_and_notification_urls_differ():
    """The two being equal is exactly the defect."""
    settings = Settings()
    assert settings.portfolio_manager_url != settings.notification_service_url
