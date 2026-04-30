import json
from datetime import UTC, datetime
from pathlib import Path

from personal_shopper.database.db import get_connection
from personal_shopper.recipes.models import Recipe


def create_run(db_path: Path) -> int:
    """Create a weekly run record and return its id."""
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO weekly_runs (started_at, status) VALUES (?, ?)",
            (now, "pending"),
        )
        return cursor.lastrowid  # type: ignore[return-value]


def store_offered_recipes(db_path: Path, run_id: int, recipes: list[Recipe]) -> list[int]:
    """Insert offered recipes for a run and return their ids."""
    ids: list[int] = []
    with get_connection(db_path) as conn:
        for recipe in recipes:
            cursor = conn.execute(
                """INSERT INTO offered_recipes
                   (run_id, title, url, prep_time_min, servings, image_url, raw_metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    recipe.title,
                    recipe.url,
                    recipe.prep_time_min,
                    recipe.servings,
                    recipe.image_url,
                    json.dumps(recipe.raw_metadata),
                ),
            )
            ids.append(cursor.lastrowid)  # type: ignore[arg-type]
    return ids


def record_selection(db_path: Path, run_id: int, offered_id: int) -> int:
    """Record a user's recipe selection and return the selected_recipe id."""
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO selected_recipes (run_id, offered_id, selected_at) VALUES (?, ?, ?)",
            (run_id, offered_id, now),
        )
        return cursor.lastrowid  # type: ignore[return-value]


def get_run_id_for_offered(db_path: Path, offered_id: int) -> int | None:
    """Return the run_id associated with an offered recipe, or None if not found."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT run_id FROM offered_recipes WHERE id = ?",
            (offered_id,),
        ).fetchone()
    return row["run_id"] if row else None
