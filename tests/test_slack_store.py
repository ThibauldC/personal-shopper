from pathlib import Path

import pytest

from personal_shopper.database.db import get_connection, init_db
from personal_shopper.recipes.models import Recipe
from personal_shopper.slack.store import (
    create_run,
    get_run_id_for_offered,
    record_selection,
    store_offered_recipes,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def recipes():
    return [
        Recipe(
            title="Pasta",
            url="https://example.com/r/R001",
            prep_time_min=20,
            servings=4,
            image_url="https://img.example.com/pasta.jpg",
        ),
        Recipe(title="Salade", url="https://example.com/r/R002"),
    ]


class TestCreateRun:
    def test_returns_positive_int(self, db_path):
        run_id = create_run(db_path)
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_creates_row_in_db(self, db_path):
        run_id = create_run(db_path)
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM weekly_runs WHERE id=?", (run_id,)).fetchone()
        assert row is not None

    def test_status_is_pending(self, db_path):
        run_id = create_run(db_path)
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT status FROM weekly_runs WHERE id=?", (run_id,)).fetchone()
        assert row["status"] == "pending"

    def test_started_at_is_set(self, db_path):
        run_id = create_run(db_path)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT started_at FROM weekly_runs WHERE id=?", (run_id,)
            ).fetchone()
        assert row["started_at"] is not None
        assert "T" in row["started_at"]

    def test_sequential_ids_are_unique(self, db_path):
        id1 = create_run(db_path)
        id2 = create_run(db_path)
        assert id1 != id2


class TestStoreOfferedRecipes:
    def test_returns_list_of_ids(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        assert isinstance(ids, list)
        assert len(ids) == len(recipes)

    def test_ids_are_positive_ints(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        assert all(isinstance(i, int) and i > 0 for i in ids)

    def test_stores_title(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT title FROM offered_recipes WHERE id=?", (ids[0],)).fetchone()
        assert row["title"] == "Pasta"

    def test_stores_url(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT url FROM offered_recipes WHERE id=?", (ids[0],)).fetchone()
        assert row["url"] == "https://example.com/r/R001"

    def test_stores_prep_time(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT prep_time_min FROM offered_recipes WHERE id=?", (ids[0],)
            ).fetchone()
        assert row["prep_time_min"] == 20

    def test_stores_none_fields(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT prep_time_min, servings FROM offered_recipes WHERE id=?", (ids[1],)
            ).fetchone()
        assert row["prep_time_min"] is None
        assert row["servings"] is None

    def test_empty_recipes_returns_empty_list(self, db_path):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, [])
        assert ids == []

    def test_run_id_linked(self, db_path, recipes):
        run_id = create_run(db_path)
        ids = store_offered_recipes(db_path, run_id, recipes)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT run_id FROM offered_recipes WHERE id=?", (ids[0],)
            ).fetchone()
        assert row["run_id"] == run_id


class TestRecordSelection:
    def test_returns_positive_int(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        sel_id = record_selection(db_path, run_id, offered_ids[0])
        assert isinstance(sel_id, int)
        assert sel_id > 0

    def test_stores_offered_id(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        sel_id = record_selection(db_path, run_id, offered_ids[0])
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT offered_id FROM selected_recipes WHERE id=?", (sel_id,)
            ).fetchone()
        assert row["offered_id"] == offered_ids[0]

    def test_stores_run_id(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        sel_id = record_selection(db_path, run_id, offered_ids[0])
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT run_id FROM selected_recipes WHERE id=?", (sel_id,)
            ).fetchone()
        assert row["run_id"] == run_id

    def test_stores_selected_at(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        sel_id = record_selection(db_path, run_id, offered_ids[0])
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT selected_at FROM selected_recipes WHERE id=?", (sel_id,)
            ).fetchone()
        assert row["selected_at"] is not None

    def test_multiple_selections_allowed(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        record_selection(db_path, run_id, offered_ids[0])
        record_selection(db_path, run_id, offered_ids[1])
        with get_connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM selected_recipes").fetchone()[0]
        assert count == 2


class TestGetRunIdForOffered:
    def test_returns_correct_run_id(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        assert get_run_id_for_offered(db_path, offered_ids[0]) == run_id

    def test_returns_none_for_unknown(self, db_path):
        assert get_run_id_for_offered(db_path, 9999) is None

    def test_returns_correct_id_for_second_recipe(self, db_path, recipes):
        run_id = create_run(db_path)
        offered_ids = store_offered_recipes(db_path, run_id, recipes)
        assert get_run_id_for_offered(db_path, offered_ids[1]) == run_id
