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
5. Under **Features → Socket Mode**, enable Socket Mode and create an **App-Level Token** with `connections:write` scope.
   - Copy the token (starts with `xapp-`) → `SLACK_APP_TOKEN`
6. Under **Features → Interactivity & Shortcuts**, enable interactivity.

   **Local dev (Socket Mode):**

   ```bash
   uv run python -m personal_shopper.slack.service
   ```

   No public Request URL or ngrok tunnel is required for button interactions.

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_PATH` | SQLite database file path | `personal_shopper.db` |
| `DELHAIZE_BASE_URL` | Delhaize website base URL | `https://www.delhaize.be` |
| `DELHAIZE_RECIPES_PER_RUN` | Number of recipes to fetch weekly | `8` |
| `DELHAIZE_REFRESH_MAX_URLS` | Optional cap for `refresh-recipes` sitemap scan (`refreshes all` when unset) | unset |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token | — |
| `SLACK_SIGNING_SECRET` | Slack app signing secret | — |
| `SLACK_APP_TOKEN` | Slack app-level token for Socket Mode (`xapp-...`) | — |
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

To run the Socket Mode listener (required to receive button interactions):

```python
from personal_shopper.slack.service import run_socket_mode
run_socket_mode()
```

## Production setup (systemd)

Use two long-running Linux services:

1. **Slack listener**: receives Slack interactions and enqueues cart jobs
2. **Cart worker**: continuously processes `cart_jobs` from SQLite

Copy service files:

```bash
sudo cp deploy/systemd/personal-shopper-slack.service /etc/systemd/system/
sudo cp deploy/systemd/personal-shopper-cart-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable and start:

```bash
sudo systemctl enable --now personal-shopper-slack.service
sudo systemctl enable --now personal-shopper-cart-worker.service
```

Inspect logs:

```bash
sudo journalctl -u personal-shopper-slack.service -f
sudo journalctl -u personal-shopper-cart-worker.service -f
```

ASCII architecture:

```text
Slack User
    |
    v
Slack Platform
    |
    | Socket Mode (WebSocket)
    v
personal-shopper-slack.service
  (personal_shopper.slack.service)
    |
    | insert cart_jobs
    v
SQLite (personal_shopper.db)
    |
    | poll pending jobs
    v
personal-shopper-cart-worker.service
  (personal_shopper.cart.worker)
    |
    | Playwright automation
    v
Delhaize cart (ingredients only)
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
