# Personal Shopper

Automates weekly meal planning and Delhaize Click & Collect grocery shopping via Slack.

## What it does

1. Fetches 8 vegetarian recipes weekly from Delhaize
2. Sends them to the user via Slack (in Dutch)
3. User selects recipes via Slack
4. Ingredients are extracted, aggregated, and merged with staple items
5. Items are matched to Delhaize products and added to the shopping cart via Playwright

## Setup

```bash
uv sync --extra dev
cp .env.example .env  # fill in your credentials
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_PATH` | SQLite database file path | `personal_shopper.db` |
| `DELHAIZE_BASE_URL` | Delhaize website base URL | `https://www.delhaize.be` |
| `DELHAIZE_RECIPES_PER_RUN` | Number of recipes to fetch weekly | `8` |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token | — |
| `SLACK_SIGNING_SECRET` | Slack app signing secret | — |
| `SLACK_CHANNEL` | Slack channel to post recipes | `#recepten` |

## Development

```bash
uv run pytest          # run tests with coverage
uv run ruff check .    # lint
```

## Manual trigger (US-004)

Send recipe options to Slack without waiting for the weekly scheduler:

```bash
uv run python main.py slack
```

This fetches 8 live recipes, persists them to the database, and posts Block Kit cards to `SLACK_CHANNEL` with a "Selecteer" button per recipe.

## Slack interaction (US-005)

Users click "Selecteer" on one or more recipe cards. Each click triggers the `select_recipe` action handler, which records the selection in `selected_recipes` and replies with a Dutch confirmation in Slack.

To run the Bolt server (required to receive button interactions):

```python
from personal_shopper.slack.bot import create_app
app = create_app()
app.start(port=3000)
```

## Architecture

```
personal_shopper/
  config.py            # pydantic-settings configuration
  database/
    schema.py          # SQLite table definitions
    db.py              # connection management
  recipes/
    models.py          # Recipe dataclass
    fetcher.py         # live Delhaize recipe scraper (httpx + BS4)
  slack/
    messages.py        # Dutch Block Kit message builder (US-004)
    store.py           # DB helpers: runs, offered/selected recipes
    bot.py             # Slack Bolt app + select_recipe handler (US-005)
```

## Phase status

- [x] Phase 0 — Core Foundation: config, database schema, recipe fetcher
- [x] Phase 1 — Slack Interaction: send recipe options (US-004), capture selections (US-005)
- [ ] Phase 2 — Ingredient processing
- [ ] Phase 3 — Product matching & cart automation
