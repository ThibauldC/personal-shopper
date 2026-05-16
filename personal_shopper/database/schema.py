SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weekly_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS offered_recipes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES weekly_runs(id),
    title           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    prep_time_min   INTEGER,
    servings        INTEGER,
    image_url       TEXT,
    raw_metadata    TEXT
);

CREATE TABLE IF NOT EXISTS selected_recipes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES weekly_runs(id),
    offered_id      INTEGER NOT NULL REFERENCES offered_recipes(id),
    selected_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ingredients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    offered_id      INTEGER NOT NULL REFERENCES offered_recipes(id),
    raw_text        TEXT    NOT NULL,
    quantity        REAL,
    unit            TEXT,
    name            TEXT,
    parsed_at       TEXT
);

CREATE TABLE IF NOT EXISTS aggregated_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES weekly_runs(id),
    name            TEXT    NOT NULL,
    quantity        REAL,
    unit            TEXT,
    source_ids      TEXT
);

CREATE TABLE IF NOT EXISTS staple_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    quantity        REAL,
    unit            TEXT,
    active          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ingredient_product_map (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_name TEXT    NOT NULL UNIQUE,
    product_id      TEXT,
    product_name    TEXT,
    product_url     TEXT,
    confidence      REAL    NOT NULL DEFAULT 1.0,
    confirmed_by_user INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_catalog (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL UNIQUE,
    title           TEXT    NOT NULL,
    prep_time_min   INTEGER,
    servings        INTEGER,
    image_url       TEXT,
    keywords        TEXT    NOT NULL,
    recipe_category TEXT,
    ingredients     TEXT    NOT NULL,
    raw_metadata    TEXT    NOT NULL,
    is_allowed      INTEGER NOT NULL,
    fetched_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cart_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    selected_recipe_id  INTEGER NOT NULL UNIQUE REFERENCES selected_recipes(id),
    status              TEXT    NOT NULL DEFAULT 'pending',
    attempts            INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    completed_at        TEXT
);
"""
