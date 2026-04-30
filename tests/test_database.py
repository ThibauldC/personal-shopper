import sqlite3
from pathlib import Path

import pytest

from personal_shopper.database.db import get_connection, init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_init_db_creates_file(tmp_path: Path):
    path = tmp_path / "new.db"
    assert not path.exists()
    init_db(path)
    assert path.exists()


def test_init_db_idempotent(tmp_path: Path):
    path = tmp_path / "idem.db"
    init_db(path)
    init_db(path)  # second call must not raise
    assert path.exists()


def test_all_tables_created(db_path: Path):
    expected_tables = {
        "weekly_runs",
        "offered_recipes",
        "selected_recipes",
        "ingredients",
        "aggregated_items",
        "staple_items",
        "ingredient_product_map",
    }
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        actual = {row["name"] for row in rows if not row["name"].startswith("sqlite_")}
    assert expected_tables == actual


def test_weekly_run_insert(db_path: Path):
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO weekly_runs (started_at, status) VALUES (?, ?)",
            ("2024-01-01T08:00:00", "pending"),
        )
        row = conn.execute("SELECT * FROM weekly_runs WHERE id=1").fetchone()
    assert row["status"] == "pending"
    assert row["started_at"] == "2024-01-01T08:00:00"


def test_offered_recipe_foreign_key(db_path: Path):
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO offered_recipes (run_id, title, url) VALUES (?, ?, ?)",
                (9999, "Ghost Recipe", "https://example.com/r/ghost"),
            )


def test_get_connection_rollback_on_error(db_path: Path):
    with pytest.raises(ValueError):
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO weekly_runs (started_at, status) VALUES (?, ?)",
                ("2024-01-01", "pending"),
            )
            raise ValueError("intentional")

    with get_connection(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM weekly_runs").fetchone()[0]
    assert count == 0


def test_staple_item_unique_constraint(db_path: Path):
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO staple_items (name) VALUES (?)", ("salt",))

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(db_path) as conn:
            conn.execute("INSERT INTO staple_items (name) VALUES (?)", ("salt",))


def test_ingredient_product_map(db_path: Path):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO ingredient_product_map
               (ingredient_name, product_id, product_name, confidence, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("tomato", "P001", "Tomaten 500g", 0.95, "2024-01-01T00:00:00"),
        )
        row = conn.execute(
            "SELECT * FROM ingredient_product_map WHERE ingredient_name='tomato'"
        ).fetchone()
    assert row["confidence"] == 0.95
    assert row["confirmed_by_user"] == 0
