import sys

from personal_shopper.config import get_settings
from personal_shopper.database.db import init_db
from personal_shopper.recipes.fetcher import refresh_recipe_catalog, sample_recipes_from_catalog
from personal_shopper.slack.bot import send_recipe_options
from personal_shopper.slack.store import create_run, store_offered_recipes


def main() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    try:
        recipes, seed = sample_recipes_from_catalog(settings=settings)
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    print(f"Random seed: {seed}")
    for i, recipe in enumerate(recipes, 1):
        prep = f"{recipe.prep_time_min} min" if recipe.prep_time_min else "?"
        print(f"{i}. {recipe.title} ({prep}) — {recipe.url}")


def refresh_recipes() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    print("Receptencatalogus verversen...")
    stored_allowed, scanned = refresh_recipe_catalog(settings=settings)
    print(f"✅ Klaar. {stored_allowed} geschikte recepten opgeslagen na {scanned} scans.")


def send_to_slack() -> None:
    """Manual trigger: fetch recipes and send options to Slack (US-004)."""
    settings = get_settings()
    init_db(settings.database_path)
    try:
        recipes, seed = sample_recipes_from_catalog(settings=settings)
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    print(f"Recepten geladen uit lokale catalogus (seed={seed})...")
    run_id = create_run(settings.database_path)
    offered_ids = store_offered_recipes(settings.database_path, run_id, recipes)
    print(f"Recepten opgeslagen (run #{run_id}). Versturen naar Slack...")
    send_recipe_options(recipes, offered_ids, settings=settings)
    print(f"✅ {len(recipes)} recepten verstuurd naar Slack!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh-recipes":
        refresh_recipes()
    elif len(sys.argv) > 1 and sys.argv[1] == "slack":
        send_to_slack()
    else:
        main()
