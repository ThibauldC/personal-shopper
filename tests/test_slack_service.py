from unittest.mock import MagicMock, patch

from personal_shopper.config import Settings
from personal_shopper.slack.service import run_socket_mode


def test_run_socket_mode_bootstraps_and_starts():
    settings = Settings(
        slack_bot_token="xoxb-test-token",
        slack_signing_secret="test-secret",
        slack_app_token="xapp-test-token",
    )
    app = MagicMock()
    handler = MagicMock()

    with patch("personal_shopper.slack.service.get_settings", return_value=settings), patch(
        "personal_shopper.slack.service.init_db"
    ) as mock_init_db, patch("personal_shopper.slack.service.create_app", return_value=app), patch(
        "personal_shopper.slack.service.SocketModeHandler", return_value=handler
    ) as mock_handler_cls:
        run_socket_mode()

    mock_init_db.assert_called_once_with(settings.database_path)
    mock_handler_cls.assert_called_once_with(app, "xapp-test-token")
    handler.start.assert_called_once()
