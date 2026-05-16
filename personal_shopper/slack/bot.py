import logging
import re
import threading
from pathlib import Path

from slack_bolt import App
from slack_sdk import WebClient

from personal_shopper.cart.automation import process_cart_job
from personal_shopper.config import Settings, get_settings
from personal_shopper.recipes.models import Recipe
from personal_shopper.slack.messages import build_recipe_blocks
from personal_shopper.slack.store import create_cart_job, get_run_id_for_offered, record_selection

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> App:
    """Create and configure the Slack Bolt app with all interaction handlers."""
    if settings is None:
        settings = get_settings()
    app = App(token=settings.slack_bot_token, signing_secret=settings.slack_signing_secret)
    _register_handlers(app, settings)
    return app


def _register_handlers(app: App, settings: Settings) -> None:
    @app.action("select_recipe")
    def handle_select_recipe(ack, action, say, body):
        _on_select_recipe(ack, action, say, body, settings)


def _on_select_recipe(ack, action, say, body: dict, settings: Settings) -> None:
    ack()
    offered_id = int(action["value"])
    db_path = settings.database_path
    run_id = get_run_id_for_offered(db_path, offered_id)
    if run_id is None:
        logger.warning("Offered recipe %d not found in DB", offered_id)
        return
    selected_recipe_id = record_selection(db_path, run_id, offered_id)
    title = _extract_title_from_body(body, offered_id)
    say(f"✅ *{title}* is toegevoegd. Ik zet ingredienten nu in de winkelkar...")

    job_id = create_cart_job(db_path, selected_recipe_id)
    if job_id is None:
        say(f"ℹ️ *{title}* stond al in de cart-queue.")
        return

    thread = threading.Thread(
        target=_process_cart_job_and_notify,
        args=(db_path, job_id, settings, say, title),
        daemon=True,
    )
    thread.start()


def _process_cart_job_and_notify(
    db_path: Path, job_id: int, settings: Settings, say, title: str
) -> None:
    succeeded = process_cart_job(db_path, job_id, settings)
    if succeeded:
        say(f"🛒 Ingredienten voor *{title}* toegevoegd aan winkelkar.")
    else:
        say(f"⚠️ Kon ingredienten voor *{title}* niet toevoegen. Check logs.")


def _extract_title_from_body(body: dict, offered_id: int) -> str:
    """Extract recipe title from Slack action payload blocks."""
    try:
        for block in body.get("message", {}).get("blocks", []):
            if block.get("type") == "section":
                accessory = block.get("accessory", {})
                if accessory.get("value") == str(offered_id):
                    text = block.get("text", {}).get("text", "")
                    m = re.search(r"\|([^>]+)>", text)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    return f"Recept #{offered_id}"


def send_recipe_options(
    recipes: list[Recipe],
    offered_ids: list[int],
    settings: Settings | None = None,
    client: WebClient | None = None,
) -> None:
    """Send recipe options to the configured Slack channel."""
    if settings is None:
        settings = get_settings()
    if client is None:
        client = WebClient(token=settings.slack_bot_token)
    blocks = build_recipe_blocks(recipes, offered_ids)
    client.chat_postMessage(
        channel=settings.slack_channel,
        text="Jouw receptopties voor deze week zijn klaar!",
        blocks=blocks,
    )
