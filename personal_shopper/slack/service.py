from slack_bolt.adapter.socket_mode import SocketModeHandler

from personal_shopper.config import get_settings
from personal_shopper.database.db import init_db
from personal_shopper.slack.bot import create_app


def run_socket_mode() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    app = create_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()


if __name__ == "__main__":
    run_socket_mode()
