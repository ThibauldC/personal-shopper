# Personal Shopper

Automates weekly meal planning and Delhaize Click & Collect grocery shopping via Slack.

## What it does

1. Builds a local catalog of vegetarian main-course recipes from Delhaize
2. Sends them to the user via Slack (in Dutch)
3. User selects recipes via Slack
4. Ingredients are extracted, aggregated, and merged with staple items
5. Items are matched to Delhaize products and added to the shopping cart via Playwright

## Setup

```bash
uv sync --extra dev
cp .env.example .env  # fill in your credentials
```

### Creating a Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App → From scratch**.
2. Give it a name (e.g. `personal-shopper`) and select your workspace.
3. Under **Settings → Basic Information**, scroll to **App Credentials**:
   - Copy **Signing Secret** → `SLACK_SIGNING_SECRET`
4. Under **Features → OAuth & Permissions**, add the bot token scopes you need (`chat:write`, `channels:read`, etc.), then click **Install to Workspace**.
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`) → `SLACK_BOT_TOKEN`
5. Under **Features → Interactivity & Shortcuts**, enable interactivity and set the **Request URL** to your server's `/slack/events` endpoint.

   **Local dev with ngrok:**

   Install ngrok if you haven't:
   ```bash
   brew install ngrok
   ngrok config add-authtoken <your-token>  # one-time, from ngrok dashboard
   ```

   In one terminal, start the Bolt server:
   ```bash
   uv run python -c "from personal_shopper.slack.bot import create_app; app = create_app(); app.start(port=3000)"
   ```

   In another terminal, expose it:
   ```bash
   ngrok http 3000
   ```

   ngrok prints a public URL like `https://abc123.ngrok-free.app`. Paste this into the Slack **Request URL** field:
   ```
   https://abc123.ngrok-free.app/slack/events
   ```

   Slack will send a verification request immediately — the Bolt server handles it automatically. Once the URL shows **Verified**, button clicks in Slack will reach your local process.

   > **Note:** the ngrok URL changes every time you restart ngrok (on the free plan). You'll need to update the Request URL in the Slack dashboard each session.

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_PATH` | SQLite database file path | `personal_shopper.db` |
| `DELHAIZE_BASE_URL` | Delhaize website base URL | `https://www.delhaize.be` |
| `DELHAIZE_RECIPES_PER_RUN` | Number of recipes to fetch weekly | `8` |
| `DELHAIZE_REFRESH_MAX_URLS` | Optional cap for `refresh-recipes` sitemap scan (`refreshes all` when unset) | unset |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token | — |
| `SLACK_SIGNING_SECRET` | Slack app signing secret | — |
| `SLACK_CHANNEL` | Slack channel to post recipes | `#recepten` |
| `DELHAIZE_USERNAME` | Delhaize account email/username | — |
| `DELHAIZE_PASSWORD` | Delhaize account password (`DELHAIZE_PWD` also supported) | — |

## Development

```bash
uv run pytest          # run tests with coverage
uv run ruff check .    # lint
```

## Recipe catalog refresh

Refresh the local recipe catalog (live scrape + strict filtering):

```bash
uv run python main.py refresh-recipes
```

This stores allowed recipes (including ingredients) in SQLite. Normal runs then pick a random sample from this local catalog.

## Manual trigger (US-004)

Send recipe options to Slack without waiting for the weekly scheduler:

```bash
uv run python main.py slack
```

This loads 8 recipes from the local catalog using a random seed, persists them to the database, and posts Block Kit cards to `SLACK_CHANNEL` with a "Selecteer" button per recipe.

## Slack interaction (US-005)

Users click "Selecteer" on one or more recipe cards. Each click triggers the `select_recipe` action handler, which records the selection in `selected_recipes` and replies with a Dutch confirmation in Slack.

Each selection also creates an async `cart_jobs` task that uses Playwright to open the recipe URL and click the recipe page add-to-cart control.

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
    fetcher.py         # catalog refresh + random local sampling
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
