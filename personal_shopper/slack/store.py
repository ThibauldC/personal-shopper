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


def create_cart_job(db_path: Path, selected_recipe_id: int) -> int | None:
    """Create a cart job. Returns None when job already exists."""
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO cart_jobs
               (selected_recipe_id, status, attempts, created_at, updated_at)
               VALUES (?, 'pending', 0, ?, ?)""",
            (selected_recipe_id, now, now),
        )
        if cursor.rowcount == 0:
            return None
        return cursor.lastrowid  # type: ignore[return-value]


def claim_cart_job(db_path: Path, job_id: int) -> bool:
    """Mark pending job as running and increment attempts."""
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """UPDATE cart_jobs
               SET status = 'running',
                   attempts = attempts + 1,
                   updated_at = ?,
                   error_message = NULL
               WHERE id = ? AND status = 'pending'""",
            (now, job_id),
        )
        return cursor.rowcount > 0


def get_cart_job_payload(db_path: Path, job_id: int) -> dict | None:
    """Return joined cart-job payload needed for automation."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT cj.id AS job_id,
                      sr.id AS selected_recipe_id,
                      o.url AS recipe_url,
                      o.title AS recipe_title
               FROM cart_jobs cj
               JOIN selected_recipes sr ON sr.id = cj.selected_recipe_id
               JOIN offered_recipes o ON o.id = sr.offered_id
               WHERE cj.id = ?""",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def mark_cart_job_succeeded(db_path: Path, job_id: int) -> None:
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE cart_jobs
               SET status = 'succeeded',
                   updated_at = ?,
                   completed_at = ?
               WHERE id = ?""",
            (now, now, job_id),
        )


def mark_cart_job_failed(db_path: Path, job_id: int, error_message: str) -> None:
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE cart_jobs
               SET status = 'failed',
                   updated_at = ?,
                   completed_at = ?,
                   error_message = ?
               WHERE id = ?""",
            (now, now, error_message[:1000], job_id),
        )
