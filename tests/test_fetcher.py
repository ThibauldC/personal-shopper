from unittest.mock import MagicMock, patch

import pytest

from personal_shopper.config import Settings
from personal_shopper.database.db import get_connection, init_db
from personal_shopper.recipes.fetcher import (
    FetchError,
    _extract_recipe_links,
    _is_allowed_recipe,
    _is_promising_recipe_url,
    _parse_recipe_detail,
    fetch_recipe_detail,
    fetch_vegetarian_recipes,
    refresh_recipe_catalog,
    sample_recipes_from_catalog,
)
from personal_shopper.recipes.models import Recipe

BASE_URL = "https://www.delhaize.be"

LISTING_HTML = """
<html><body>
  <a href="/r/R00001">Pasta</a>
  <a href="/r/R00002">Salade</a>
  <a href="/r/R00003">Soep</a>
  <a href="/nl/r/R00004">Veg Curry</a>
  <a href="/r/R00001">Pasta</a>
  <a href="/other/page">Other</a>
  <a href="/products/cheese">Cheese</a>
</body></html>
"""

RECIPE_HTML = """
<html>
<head><meta property="og:image" content="https://img.example.com/pasta.jpg"/></head>
<body>
  <h1>Veggie Pasta Pesto</h1>
  <p>Bereidingstijd: 25 min. | Moeilijkheid: Makkelijk</p>
  <p>4 porties</p>
  <ul>
    <li><strong>500 g</strong> volkoren spaghetti</li>
    <li><strong>2 el</strong> pesto</li>
    <li><strong>50 g</strong> pijnboompitten</li>
  </ul>
  <script id="recipe-seo-data" type="application/ld+json">
  {
    "@context": "http://schema.org/",
    "@type": "Recipe",
    "keywords": "Vegetarisch, Diner, Hoofdgerecht",
    "recipeCategory": "Diner",
    "recipeIngredient": ["spaghetti", "pesto", "rucola"]
  }
  </script>
</body>
</html>
"""

RECIPE_HTML_NO_PREP = """
<html>
<body>
  <h1>Simple Salad</h1>
  <p>2 porties</p>
  <ul><li><strong>100 g</strong> sla</li></ul>
</body>
</html>
"""

RECIPE_HTML_DESSERT = """
<html>
<body>
  <h1>Tiramisu</h1>
  <script id="recipe-seo-data" type="application/ld+json">
  {
    "@context": "http://schema.org/",
    "@type": "Recipe",
    "keywords": "Vegetarisch, Dessert",
    "recipeCategory": "Dessert",
    "recipeIngredient": ["mascarpone", "koffie"]
  }
  </script>
</body>
</html>
"""

RECIPE_HTML_FISH = """
<html>
<body>
  <h1>Pasta met zalm</h1>
  <script id="recipe-seo-data" type="application/ld+json">
  {
    "@context": "http://schema.org/",
    "@type": "Recipe",
    "keywords": "Vegetarisch, Diner, Hoofdgerecht",
    "recipeCategory": "Diner",
    "recipeIngredient": ["zalm", "pasta"]
  }
  </script>
</body>
</html>
"""

RECIPE_HTML_DRINK = """
<html>
<body>
  <h1>Frisse mocktail</h1>
  <script id="recipe-seo-data" type="application/ld+json">
  {
    "@context": "http://schema.org/",
    "@type": "Recipe",
    "keywords": "Vegan, Dranken",
    "recipeCategory": "Overig",
    "recipeIngredient": ["limoensap", "ijs"]
  }
  </script>
</body>
</html>
"""


class TestExtractRecipeLinks:
    def test_extracts_valid_links(self):
        links = _extract_recipe_links(LISTING_HTML, BASE_URL)
        assert f"{BASE_URL}/r/R00001" in links
        assert f"{BASE_URL}/r/R00002" in links
        assert f"{BASE_URL}/r/R00003" in links
        assert f"{BASE_URL}/r/R00004" in links

    def test_deduplicates(self):
        links = _extract_recipe_links(LISTING_HTML, BASE_URL)
        assert links.count(f"{BASE_URL}/r/R00001") == 1

    def test_excludes_non_recipe_links(self):
        links = _extract_recipe_links(LISTING_HTML, BASE_URL)
        assert not any("/other/" in url for url in links)
        assert not any("/products/" in url for url in links)

    def test_normalizes_nl_recipe_links(self):
        html = """
        <html><body>
          <a href="/nl/r/R00001">Pasta NL</a>
          <a href="/r/R00001">Pasta</a>
        </body></html>
        """
        links = _extract_recipe_links(html, BASE_URL)
        assert links == [f"{BASE_URL}/r/R00001"]

    def test_empty_html(self):
        assert _extract_recipe_links("<html></html>", BASE_URL) == []


class TestParseRecipeDetail:
    def test_parses_title(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert recipe.title == "Veggie Pasta Pesto"

    def test_parses_prep_time(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert recipe.prep_time_min == 25

    def test_parses_servings(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert recipe.servings == 4

    def test_parses_image_url_from_og(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert recipe.image_url == "https://img.example.com/pasta.jpg"

    def test_url_preserved(self):
        url = f"{BASE_URL}/r/R00001"
        recipe = _parse_recipe_detail(RECIPE_HTML, url)
        assert recipe.url == url

    def test_missing_prep_time(self):
        recipe = _parse_recipe_detail(RECIPE_HTML_NO_PREP, f"{BASE_URL}/r/R00002")
        assert recipe.prep_time_min is None

    def test_returns_recipe_instance(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert isinstance(recipe, Recipe)

    def test_parses_metadata_keywords(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert "Vegetarisch" in recipe.keywords

    def test_parses_metadata_ingredients(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert "rucola" in recipe.ingredients


class TestStrictFilter:
    def test_accepts_vegetarian_main_course(self):
        recipe = _parse_recipe_detail(RECIPE_HTML, f"{BASE_URL}/r/R00001")
        assert _is_allowed_recipe(recipe)

    def test_rejects_dessert(self):
        recipe = _parse_recipe_detail(RECIPE_HTML_DESSERT, f"{BASE_URL}/r/R00009")
        assert not _is_allowed_recipe(recipe)

    def test_rejects_fish_even_if_keyword_says_vegetarian(self):
        recipe = _parse_recipe_detail(RECIPE_HTML_FISH, f"{BASE_URL}/r/R00010")
        assert not _is_allowed_recipe(recipe)


class TestFetchRecipeDetail:
    def test_raises_fetch_error_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        with pytest.raises(FetchError) as exc_info:
            fetch_recipe_detail(f"{BASE_URL}/r/R00001", client=mock_client)
        assert exc_info.value.status_code == 404

    def test_returns_recipe_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = RECIPE_HTML
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        recipe = fetch_recipe_detail(f"{BASE_URL}/r/R00001", client=mock_client)
        assert recipe.title == "Veggie Pasta Pesto"

    def test_fetch_error_str(self):
        err = FetchError(url="https://example.com", status_code=503)
        assert "503" in str(err)
        assert "example.com" in str(err)


class TestFetchVegetarianRecipes:
    def _make_mock_client(self, listing_html: str, detail_html: str):
        def get(url: str, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "/r/" in url:
                resp.text = detail_html
            else:
                resp.text = listing_html
            return resp

        client = MagicMock()
        client.get.side_effect = get
        client.__enter__ = lambda s: s
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_returns_requested_count(self):
        settings = Settings(delhaize_recipes_per_run=2)
        big_listing = LISTING_HTML  # has 3 unique recipe links

        with patch("personal_shopper.recipes.fetcher._make_client") as mock_factory:
            mock_factory.return_value = self._make_mock_client(big_listing, RECIPE_HTML)
            recipes = fetch_vegetarian_recipes(count=2, settings=settings)

        assert len(recipes) == 2

    def test_returns_recipe_objects(self):
        settings = Settings(delhaize_recipes_per_run=3)

        with patch("personal_shopper.recipes.fetcher._make_client") as mock_factory:
            mock_factory.return_value = self._make_mock_client(LISTING_HTML, RECIPE_HTML)
            recipes = fetch_vegetarian_recipes(count=3, settings=settings)

        assert all(isinstance(r, Recipe) for r in recipes)

    def test_skips_failed_detail_pages(self):
        settings = Settings(delhaize_recipes_per_run=3)

        def get(url: str, **kwargs):
            resp = MagicMock()
            if "/r/R00001" in url:
                resp.status_code = 500
            elif "/r/" in url:
                resp.status_code = 200
                resp.text = RECIPE_HTML
            else:
                resp.status_code = 200
                resp.text = LISTING_HTML
            return resp

        client = MagicMock()
        client.get.side_effect = get
        client.__enter__ = lambda s: s
        client.__exit__ = MagicMock(return_value=False)

        with patch("personal_shopper.recipes.fetcher._make_client", return_value=client):
            recipes = fetch_vegetarian_recipes(count=3, settings=settings)

        assert len(recipes) == 3  # R00002, R00003 and R00004 succeed; R00001 skipped

    def test_skips_failed_listing_pages(self):
        settings = Settings(delhaize_recipes_per_run=3)

        call_count = 0

        def get(url: str, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if "/r/" in url:
                resp.status_code = 200
                resp.text = RECIPE_HTML
            elif call_count == 1:
                resp.status_code = 503  # first listing fails
                resp.text = ""
            else:
                resp.status_code = 200
                resp.text = LISTING_HTML
            return resp

        client = MagicMock()
        client.get.side_effect = get
        client.__enter__ = lambda s: s
        client.__exit__ = MagicMock(return_value=False)

        with patch("personal_shopper.recipes.fetcher._make_client", return_value=client):
            recipes = fetch_vegetarian_recipes(count=2, settings=settings)

        assert len(recipes) == 2


class TestSampleRecipesFromCatalog:
    def test_returns_random_sample_with_seed(self, tmp_path):
        db_path = tmp_path / "catalog.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_recipes_per_run=2)

        with get_connection(db_path) as conn:
            for idx in range(1, 6):
                conn.execute(
                    """INSERT INTO recipe_catalog
                       (url, title, prep_time_min, servings, image_url, keywords,
                        recipe_category, ingredients, raw_metadata, is_allowed, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"https://www.delhaize.be/r/R{idx}",
                        f"Recipe {idx}",
                        20,
                        2,
                        None,
                        '["Vegetarisch", "Diner"]',
                        "Diner",
                        '["ingredient"]',
                        "{}",
                        1,
                        "2026-01-01T00:00:00+00:00",
                    ),
                )

        sample_a, seed_a = sample_recipes_from_catalog(settings=settings, seed=123)
        sample_b, seed_b = sample_recipes_from_catalog(settings=settings, seed=123)

        assert seed_a == 123
        assert seed_b == 123
        assert [recipe.url for recipe in sample_a] == [recipe.url for recipe in sample_b]
        assert len(sample_a) == 2

    def test_raises_when_catalog_too_small(self, tmp_path):
        db_path = tmp_path / "catalog_small.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_recipes_per_run=2)

        with pytest.raises(ValueError):
            sample_recipes_from_catalog(settings=settings)

    def test_filters_stale_disallowed_rows_defensively(self, tmp_path):
        db_path = tmp_path / "catalog_stale.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_recipes_per_run=1)

        with get_connection(db_path) as conn:
            conn.execute(
                """INSERT INTO recipe_catalog
                   (url, title, prep_time_min, servings, image_url, keywords,
                    recipe_category, ingredients, raw_metadata, is_allowed, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "https://www.delhaize.be/r/R-stale",
                    "Mocktail",
                    5,
                    1,
                    None,
                    '["Vegan", "Dranken"]',
                    "Overig",
                    '["limoensap"]',
                    "{}",
                    1,
                    "2026-01-01T00:00:00+00:00",
                ),
            )

        with pytest.raises(ValueError):
            sample_recipes_from_catalog(settings=settings, seed=123)


class TestRecipeUrlPrefilter:
    def test_rejects_obvious_dessert_slug(self):
        url = "https://www.delhaize.be/nl/recepten/receptDetails/choco-brownie/r/R999"
        assert not _is_promising_recipe_url(url)

    def test_accepts_generic_recipe_url(self):
        url = "https://www.delhaize.be/r/R12345"
        assert _is_promising_recipe_url(url)


class TestRefreshRecipeCatalog:
    def test_full_sitemap_scan_when_no_limit_set(self, tmp_path):
        db_path = tmp_path / "catalog_refresh.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_refresh_max_urls=None)

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("personal_shopper.recipes.fetcher._make_client", return_value=mock_client), patch(
            "personal_shopper.recipes.fetcher._extract_recipe_links_from_sitemap", return_value=[]
        ) as mock_extract:
            stored_allowed, scanned = refresh_recipe_catalog(settings=settings)

        assert stored_allowed == 0
        assert scanned == 0
        mock_extract.assert_called_once_with(client=mock_client, limit=None)

    def test_uses_env_limit_for_sitemap_scan(self, tmp_path):
        db_path = tmp_path / "catalog_refresh_limited.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_refresh_max_urls=123)

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("personal_shopper.recipes.fetcher._make_client", return_value=mock_client), patch(
            "personal_shopper.recipes.fetcher._extract_recipe_links_from_sitemap", return_value=[]
        ) as mock_extract:
            stored_allowed, scanned = refresh_recipe_catalog(settings=settings)

        assert stored_allowed == 0
        assert scanned == 0
        mock_extract.assert_called_once_with(client=mock_client, limit=123)

    def test_marks_disallowed_recipe_as_not_allowed(self, tmp_path):
        db_path = tmp_path / "catalog_refresh_filtering.db"
        init_db(db_path)
        settings = Settings(database_path=db_path, delhaize_refresh_max_urls=1)

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)

        detail_url = "https://www.delhaize.be/nl/recepten/receptDetails/mocktail/r/R777"

        def get(url: str, **kwargs):
            resp = MagicMock()
            if url == detail_url:
                resp.status_code = 200
                resp.text = RECIPE_HTML_DRINK
            else:
                resp.status_code = 200
                resp.text = ""
                resp.content = b""
            return resp

        mock_client.get.side_effect = get

        with patch("personal_shopper.recipes.fetcher._make_client", return_value=mock_client), patch(
            "personal_shopper.recipes.fetcher._extract_recipe_links_from_sitemap", return_value=[detail_url]
        ):
            stored_allowed, scanned = refresh_recipe_catalog(settings=settings)

        assert stored_allowed == 0
        assert scanned == 1

        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT is_allowed FROM recipe_catalog WHERE url = ?",
                (detail_url,),
            ).fetchone()

        assert row is not None
        assert row["is_allowed"] == 0
