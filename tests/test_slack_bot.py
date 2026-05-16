from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from personal_shopper.config import Settings
from personal_shopper.database.db import init_db
from personal_shopper.recipes.models import Recipe
from personal_shopper.slack.bot import (
    _extract_title_from_body,
    _on_select_recipe,
    _process_cart_job_and_notify,
    create_app,
    send_recipe_options,
)
from personal_shopper.slack.store import create_run, store_offered_recipes


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def settings(db_path):
    return Settings(
        slack_bot_token="xoxb-test-token",
        slack_signing_secret="test-secret",
        slack_channel="#recepten",
        database_path=db_path,
    )


@pytest.fixture
def recipe():
    return Recipe(
        title="Pasta Pesto",
        url="https://example.com/r/R001",
        prep_time_min=25,
        servings=4,
    )


class TestExtractTitleFromBody:
    def test_extracts_title_from_blocks(self):
        body = {
            "message": {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*<https://example.com/r/R001|Pasta Pesto>*",
                        },
                        "accessory": {"type": "button", "value": "1"},
                    }
                ]
            }
        }
        assert _extract_title_from_body(body, 1) == "Pasta Pesto"

    def test_fallback_when_no_match(self):
        result = _extract_title_from_body({}, 42)
        assert "42" in result

    def test_fallback_when_offered_id_mismatch(self):
        body = {
            "message": {
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "*<https://example.com|Pasta>*"},
                        "accessory": {"type": "button", "value": "99"},
                    }
                ]
            }
        }
        result = _extract_title_from_body(body, 1)
        assert "1" in result

    def test_fallback_when_blocks_missing(self):
        result = _extract_title_from_body({"message": {}}, 5)
        assert "5" in result

    def test_fallback_on_non_section_block(self):
        body = {
            "message": {
                "blocks": [{"type": "divider"}]
            }
        }
        result = _extract_title_from_body(body, 3)
        assert "3" in result

    def test_fallback_on_exception(self):
        result = _extract_title_from_body({"message": {"blocks": None}}, 7)
        assert "7" in result


class TestOnSelectRecipe:
    def test_records_selection_in_db(self, db_path, recipe):
        from personal_shopper.database.db import get_connection

        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, [recipe])

        ack = MagicMock()
        say = MagicMock()
        settings = Settings(database_path=db_path)
        with patch("personal_shopper.slack.bot.threading.Thread") as mock_thread:
            _on_select_recipe(ack, {"value": str(offered_ids[0])}, say, {}, settings)
            mock_thread.assert_called_once()

        ack.assert_called_once()
        with get_connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM selected_recipes").fetchone()[0]
        assert count == 1

    def test_say_called_with_confirmation(self, db_path, recipe):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, [recipe])

        say = MagicMock()
        settings = Settings(database_path=db_path)
        with patch("personal_shopper.slack.bot.threading.Thread"):
            _on_select_recipe(MagicMock(), {"value": str(offered_ids[0])}, say, {}, settings)

        assert say.call_count >= 1
        assert "toegevoegd" in say.call_args_list[0][0][0]

    def test_say_includes_title_from_body(self, db_path, recipe):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, [recipe])
        body = {
            "message": {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*<https://example.com|Pasta Pesto>*",
                        },
                        "accessory": {"type": "button", "value": str(offered_ids[0])},
                    }
                ]
            }
        }
        say = MagicMock()
        settings = Settings(database_path=db_path)
        with patch("personal_shopper.slack.bot.threading.Thread"):
            _on_select_recipe(MagicMock(), {"value": str(offered_ids[0])}, say, body, settings)
        assert "Pasta Pesto" in say.call_args_list[0][0][0]

    def test_unknown_offered_id_no_say(self, db_path):
        ack = MagicMock()
        say = MagicMock()
        settings = Settings(database_path=db_path)
        _on_select_recipe(ack, {"value": "9999"}, say, {}, settings)
        ack.assert_called_once()
        say.assert_not_called()

    def test_ack_always_called(self, db_path):
        ack = MagicMock()
        settings = Settings(database_path=db_path)
        _on_select_recipe(ack, {"value": "9999"}, MagicMock(), {}, settings)
        ack.assert_called_once()


class TestProcessCartJobAndNotify:
    def test_sends_success_message(self, db_path):
        say = MagicMock()
        settings = Settings(database_path=db_path)
        with patch("personal_shopper.slack.bot.process_cart_job", return_value=True):
            _process_cart_job_and_notify(db_path, 1, settings, say, "Pasta")
        assert "toegevoegd" in say.call_args[0][0]

    def test_sends_failure_message(self, db_path):
        say = MagicMock()
        settings = Settings(database_path=db_path)
        with patch("personal_shopper.slack.bot.process_cart_job", return_value=False):
            _process_cart_job_and_notify(db_path, 1, settings, say, "Pasta")
        assert "Kon ingredienten" in say.call_args[0][0]


class TestSendRecipeOptions:
    def test_calls_chat_post_message(self, settings, recipe):
        mock_client = MagicMock()
        send_recipe_options([recipe], [1], settings=settings, client=mock_client)
        mock_client.chat_postMessage.assert_called_once()

    def test_sends_to_correct_channel(self, settings, recipe):
        mock_client = MagicMock()
        send_recipe_options([recipe], [1], settings=settings, client=mock_client)
        kwargs = mock_client.chat_postMessage.call_args[1]
        assert kwargs["channel"] == "#recepten"

    def test_includes_blocks(self, settings, recipe):
        mock_client = MagicMock()
        send_recipe_options([recipe], [1], settings=settings, client=mock_client)
        kwargs = mock_client.chat_postMessage.call_args[1]
        assert "blocks" in kwargs
        assert len(kwargs["blocks"]) > 0

    def test_includes_fallback_text(self, settings, recipe):
        mock_client = MagicMock()
        send_recipe_options([recipe], [1], settings=settings, client=mock_client)
        kwargs = mock_client.chat_postMessage.call_args[1]
        assert "text" in kwargs
        assert kwargs["text"]

    def test_recipe_title_in_blocks(self, settings, recipe):
        mock_client = MagicMock()
        send_recipe_options([recipe], [1], settings=settings, client=mock_client)
        blocks = mock_client.chat_postMessage.call_args[1]["blocks"]
        assert any("Pasta Pesto" in str(b) for b in blocks)

    def test_creates_web_client_when_none(self, settings, recipe):
        with patch("personal_shopper.slack.bot.WebClient") as mock_web_client:
            mock_instance = MagicMock()
            mock_web_client.return_value = mock_instance
            send_recipe_options([recipe], [1], settings=settings)
            mock_web_client.assert_called_once_with(token="xoxb-test-token")
            mock_instance.chat_postMessage.assert_called_once()


class TestCreateApp:
    def test_creates_bolt_app(self, settings):
        with patch("personal_shopper.slack.bot.App") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            app = create_app(settings)
            assert app is mock_app
            mock_app_cls.assert_called_once_with(
                token="xoxb-test-token", signing_secret="test-secret"
            )

    def test_uses_default_settings_when_none(self):
        mock_settings = Settings(
            slack_bot_token="xoxb-default",
            slack_signing_secret="default-secret",
            slack_channel="#test",
        )
        with patch("personal_shopper.slack.bot.App") as mock_app_cls, \
             patch("personal_shopper.slack.bot.get_settings", return_value=mock_settings):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            app = create_app()
            assert app is mock_app
