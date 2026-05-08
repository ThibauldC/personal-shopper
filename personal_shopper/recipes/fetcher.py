import logging
import json
import gzip
import random
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from personal_shopper.config import Settings, get_settings
from personal_shopper.database.db import get_connection
from personal_shopper.recipes.models import Recipe

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
# httpx is very chatty at DEBUG; keep it at INFO so we still see request lines.
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("httpcore").setLevel(logging.INFO)

logger = logging.getLogger("personal_shopper.fetcher")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-BE,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_RECIPE_LINK_RE = re.compile(r"^/(?:nl/)?r/[A-Za-z0-9]+$")
_PREP_TIME_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)
_SERVINGS_RE = re.compile(r"(\d+)\s*porti", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_SITEMAP_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
_RECIPE_DETAIL_URL_RE = re.compile(r"https://www\.delhaize\.be/nl/recepten/receptDetails/[^\s<]+/r/([A-Za-z0-9]+)$")
_RECIPE_SLUG_RE = re.compile(r"/receptDetails/([^/]+)/r/[A-Za-z0-9]+$")

_ALLOWED_KEYWORDS = {"vegetarisch", "vegan"}
_REQUIRED_KEYWORDS = {"hoofdgerecht", "diner"}
_DISALLOWED_KEYWORDS = {
    "dessert",
    "desserts",
    "desserts en snacks",
    "snack",
    "snacks",
    "ontbijt",
    "lunch",
    "aperitief",
    "apero",
    "voorgerecht",
    "soep",
    "salade",
}
_NON_VEG_TERMS = {
    "kip",
    "kalkoen",
    "spek",
    "ham",
    "gehakt",
    "rund",
    "runds",
    "rundvlees",
    "varken",
    "varkens",
    "varkensvlees",
    "filet pur",
    "chorizo",
    "worst",
    "salami",
    "eend",
    "konijn",
    "paté",
    "tonijn",
    "zalm",
    "kabeljauw",
    "schelvis",
    "forel",
    "vis",
    "garnalen",
    "garnaal",
    "scampi",
    "mossel",
    "mosselen",
    "gamba",
    "gambas",
    "kreeft",
    "oester",
    "ansjovis",
    "sardien",
    "sardines",
    "haring",
    "balletjes",
}
_URL_DISALLOWED_TERMS = _NON_VEG_TERMS | {
    "dessert",
    "desserts",
    "brownie",
    "brownies",
    "tiramisu",
    "panna",
    "baklava",
    "cake",
    "taart",
    "koek",
    "cookie",
    "cocktail",
    "drank",
    "drankjes",
}


@dataclass
class FetchError(Exception):
    url: str
    status_code: int

    def __str__(self) -> str:
        return f"HTTP {self.status_code} for {self.url}"


def _make_client(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)


def _extract_recipe_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    urls: list[str] = []
    for tag in soup.find_all("a", href=_RECIPE_LINK_RE):
        href: str = tag["href"]
        if href.startswith("/nl/r/"):
            href = href.removeprefix("/nl")
        if href not in seen:
            seen.add(href)
            urls.append(f"{base_url}{href}")
    return urls


def _parse_recipe_detail(html: str, url: str) -> Recipe:
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else url.split("/")[-1]

    prep_time_min: int | None = None
    servings: int | None = None

    page_text = soup.get_text(" ")
    m = _PREP_TIME_RE.search(page_text)
    if m:
        prep_time_min = int(m.group(1))

    m = _SERVINGS_RE.search(page_text)
    if m:
        servings = int(m.group(1))

    image_url: str | None = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"]
    else:
        main_img = soup.find("img", alt=title)
        if main_img and main_img.get("src"):
            image_url = main_img["src"]

    metadata = _extract_recipe_metadata(soup)
    keywords = metadata.get("keywords", [])
    recipe_category = metadata.get("recipe_category")
    ingredients = metadata.get("ingredients", [])

    return Recipe(
        title=title,
        url=url,
        prep_time_min=prep_time_min,
        servings=servings,
        image_url=image_url,
        keywords=keywords,
        recipe_category=recipe_category,
        ingredients=ingredients,
        raw_metadata=metadata,
    )


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def _extract_recipe_metadata(soup: BeautifulSoup) -> dict:
    metadata: dict = {}
    script_tag = soup.find("script", attrs={"type": "application/ld+json", "id": "recipe-seo-data"})
    if not script_tag:
        return metadata

    raw_content = script_tag.string or script_tag.get_text(strip=True)
    if not raw_content:
        return metadata

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.debug("Could not parse JSON-LD recipe metadata")
        return metadata

    keywords_raw = payload.get("keywords", "")
    if isinstance(keywords_raw, str):
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    elif isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    else:
        keywords = []

    category = payload.get("recipeCategory")
    category_str = str(category).strip() if category else None

    ingredients_raw = payload.get("recipeIngredient", [])
    ingredients = [str(i).strip() for i in ingredients_raw if str(i).strip()] if isinstance(ingredients_raw, list) else []

    metadata["keywords"] = keywords
    metadata["recipe_category"] = category_str
    metadata["ingredients"] = ingredients
    return metadata


def _is_allowed_recipe(recipe: Recipe) -> bool:
    normalized_keywords = {_normalize_text(k) for k in recipe.keywords if k}
    category = _normalize_text(recipe.recipe_category) if recipe.recipe_category else ""
    text_blob = _normalize_text(" ".join([recipe.title, *recipe.ingredients]))

    has_allowed_keyword = bool(normalized_keywords & _ALLOWED_KEYWORDS)
    has_required_meal = bool(normalized_keywords & _REQUIRED_KEYWORDS) or category in _REQUIRED_KEYWORDS
    has_disallowed_meal = bool(normalized_keywords & _DISALLOWED_KEYWORDS) or category in _DISALLOWED_KEYWORDS
    has_non_veg_term = any(term in text_blob for term in _NON_VEG_TERMS)

    return has_allowed_keyword and has_required_meal and not has_disallowed_meal and not has_non_veg_term


def _extract_recipe_links_from_sitemap(client: httpx.Client, limit: int | None = None) -> list[str]:
    index_url = "https://www.delhaize.be/sitemapnl/delhaizesitemapindex.xml"
    logger.info("GET sitemap index %s", index_url)
    t0 = time.monotonic()
    resp = client.get(index_url)
    logger.info("  -> %s in %.2fs (%d bytes)", resp.status_code, time.monotonic() - t0, len(resp.content))
    if resp.status_code != 200:
        return []

    sitemap_urls = _SITEMAP_LOC_RE.findall(resp.text)
    if not sitemap_urls:
        return []

    collected: list[str] = []
    seen: set[str] = set()

    for sitemap_url in sitemap_urls:
        logger.info("GET sitemap chunk %s", sitemap_url)
        t1 = time.monotonic()
        chunk = client.get(sitemap_url)
        logger.info("  -> %s in %.2fs (%d bytes)", chunk.status_code, time.monotonic() - t1, len(chunk.content))
        if chunk.status_code != 200:
            continue

        try:
            xml_text = gzip.decompress(chunk.content).decode("utf-8", errors="ignore")
        except OSError:
            xml_text = chunk.text

        for loc in _SITEMAP_LOC_RE.findall(xml_text):
            m = _RECIPE_DETAIL_URL_RE.match(loc)
            if not m:
                continue
            if not _is_promising_recipe_url(loc):
                continue
            if loc not in seen:
                seen.add(loc)
                collected.append(loc)
                if limit is not None and len(collected) >= limit:
                    return collected

    return collected


def _is_promising_recipe_url(url: str) -> bool:
    match = _RECIPE_SLUG_RE.search(url)
    if not match:
        return True
    slug = _normalize_text(match.group(1).replace("-", " "))
    return not any(term in slug for term in _URL_DISALLOWED_TERMS)


def _collect_candidate_recipe_urls(
    settings: Settings,
    client: httpx.Client,
    max_candidate_urls: int,
) -> list[str]:
    listing_urls = [
        f"{settings.delhaize_base_url}/nl/recepten",
        f"{settings.delhaize_base_url}/nl/recepten/hoofdgerechten",
        f"{settings.delhaize_base_url}/nl/recepten/wereldkeuken/",
        f"{settings.delhaize_base_url}/nl/recepten/italiaans",
        f"{settings.delhaize_base_url}/nl/recepten/aziatisch",
        f"{settings.delhaize_base_url}/nl/recepten/vegetarisch",
        f"{settings.delhaize_base_url}/nl/recepten/vegan",
        f"{settings.delhaize_base_url}/nl/plantbased",
        f"{settings.delhaize_base_url}/nl/recepten/salades",
        f"{settings.delhaize_base_url}/nl/recepten/soep/",
    ]
    logger.info("listing urls: %s", listing_urls)

    recipe_urls: list[str] = []
    seen_urls: set[str] = set()

    for listing_url in listing_urls:
        if len(recipe_urls) >= max_candidate_urls:
            logger.info("collected enough listing urls (%d), stopping", len(recipe_urls))
            break
        logger.info("GET listing %s", listing_url)
        t0 = time.monotonic()
        try:
            resp = client.get(listing_url)
            logger.info(
                "  -> %s in %.2fs (%d bytes)",
                resp.status_code,
                time.monotonic() - t0,
                len(resp.content),
            )
            if resp.status_code != 200:
                logger.warning("  skipping (non-200)")
                continue
            found = _extract_recipe_links(resp.text, settings.delhaize_base_url)
            logger.info("  found %d recipe links on listing", len(found))
            for url in found:
                if url not in seen_urls:
                    seen_urls.add(url)
                    recipe_urls.append(url)
        except httpx.RequestError as e:
            logger.warning("  request error after %.2fs: %r", time.monotonic() - t0, e)
            continue

    logger.info("total unique recipe urls collected: %d", len(recipe_urls))

    if len(recipe_urls) < max_candidate_urls:
        needed = max_candidate_urls - len(recipe_urls)
        logger.info("collecting additional candidates from sitemap (need up to %d)", needed)
        sitemap_urls = _extract_recipe_links_from_sitemap(client=client, limit=max_candidate_urls)
        added = 0
        for url in sitemap_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                recipe_urls.append(url)
                added += 1
                if len(recipe_urls) >= max_candidate_urls:
                    break
        logger.info("added %d sitemap candidates; total now %d", added, len(recipe_urls))

    return recipe_urls


def refresh_recipe_catalog(
    settings: Settings | None = None,
    max_candidate_urls: int | None = None,
) -> tuple[int, int]:
    if settings is None:
        settings = get_settings()
    if max_candidate_urls is None:
        max_candidate_urls = settings.delhaize_refresh_max_urls

    if max_candidate_urls is None:
        logger.info("refresh_recipe_catalog start (full sitemap scan)")
    else:
        logger.info("refresh_recipe_catalog start (sitemap capped at %d URLs)", max_candidate_urls)

    scanned_count = 0
    stored_allowed_count = 0
    now = datetime.now(UTC).isoformat()

    with _make_client() as client:
        recipe_urls = _extract_recipe_links_from_sitemap(client=client, limit=max_candidate_urls)
        logger.info("collected %d recipe URLs from sitemap", len(recipe_urls))
        with get_connection(settings.database_path) as conn:
            for idx, url in enumerate(recipe_urls, 1):
                scanned_count += 1
                logger.info("[%d/%d] refreshing detail", idx, len(recipe_urls))
                try:
                    recipe = fetch_recipe_detail(url, client=client)
                except (FetchError, httpx.RequestError) as e:
                    logger.warning("  detail fetch failed: %r", e)
                    continue

                is_allowed = _is_allowed_recipe(recipe)
                if is_allowed:
                    stored_allowed_count += 1

                conn.execute(
                    """INSERT INTO recipe_catalog
                       (url, title, prep_time_min, servings, image_url, keywords,
                        recipe_category, ingredients, raw_metadata, is_allowed, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET
                         title = excluded.title,
                         prep_time_min = excluded.prep_time_min,
                         servings = excluded.servings,
                         image_url = excluded.image_url,
                         keywords = excluded.keywords,
                         recipe_category = excluded.recipe_category,
                         ingredients = excluded.ingredients,
                         raw_metadata = excluded.raw_metadata,
                          is_allowed = excluded.is_allowed,
                          fetched_at = excluded.fetched_at""",
                    (
                        recipe.url,
                        recipe.title,
                        recipe.prep_time_min,
                        recipe.servings,
                        recipe.image_url,
                        json.dumps(recipe.keywords),
                        recipe.recipe_category,
                        json.dumps(recipe.ingredients),
                        json.dumps(recipe.raw_metadata),
                        1 if is_allowed else 0,
                        now,
                    ),
                )

    logger.info(
        "refresh_recipe_catalog done: stored %d allowed from %d scanned",
        stored_allowed_count,
        scanned_count,
    )
    return stored_allowed_count, scanned_count


def sample_recipes_from_catalog(
    count: int | None = None,
    settings: Settings | None = None,
    seed: int | None = None,
) -> tuple[list[Recipe], int]:
    if settings is None:
        settings = get_settings()
    if count is None:
        count = settings.delhaize_recipes_per_run
    if seed is None:
        seed = random.SystemRandom().randint(1, 2_147_483_647)

    with get_connection(settings.database_path) as conn:
        rows = conn.execute(
            """SELECT url, title, prep_time_min, servings, image_url, keywords,
                      recipe_category, ingredients, raw_metadata
               FROM recipe_catalog
               WHERE is_allowed = 1"""
        ).fetchall()

    recipes: list[Recipe] = []
    for row in rows:
        try:
            keywords = json.loads(row["keywords"] or "[]")
            ingredients = json.loads(row["ingredients"] or "[]")
            raw_metadata = json.loads(row["raw_metadata"] or "{}")
        except (TypeError, json.JSONDecodeError, sqlite3.Error):
            keywords = []
            ingredients = []
            raw_metadata = {}
        recipe = Recipe(
            title=row["title"],
            url=row["url"],
            prep_time_min=row["prep_time_min"],
            servings=row["servings"],
            image_url=row["image_url"],
            keywords=keywords,
            recipe_category=row["recipe_category"],
            ingredients=ingredients,
            raw_metadata=raw_metadata,
        )
        if _is_allowed_recipe(recipe):
            recipes.append(recipe)

    if len(recipes) < count:
        raise ValueError(
            f"Not enough recipes in local catalog ({len(recipes)}/{count}). "
            "Run `uv run python main.py refresh-recipes` first."
        )

    rng = random.Random(seed)
    return rng.sample(recipes, count), seed


def fetch_recipe_detail(url: str, client: httpx.Client | None = None) -> Recipe:
    """Fetch and parse a single recipe detail page. Always live, no caching."""
    own_client = client is None
    if own_client:
        client = _make_client()
    try:
        logger.info("GET recipe detail %s", url)
        t0 = time.monotonic()
        resp = client.get(url)
        logger.info("  -> %s in %.2fs (%d bytes)", resp.status_code, time.monotonic() - t0, len(resp.content))
        if resp.status_code != 200:
            raise FetchError(url=url, status_code=resp.status_code)
        return _parse_recipe_detail(resp.text, url)
    finally:
        if own_client:
            client.close()


def fetch_vegetarian_recipes(
    count: int | None = None,
    settings: Settings | None = None,
) -> list[Recipe]:
    """Fetch `count` vegetarian recipes live from Delhaize. No caching."""
    if settings is None:
        settings = get_settings()
    if count is None:
        count = settings.delhaize_recipes_per_run

    max_candidate_urls = max(count * 20, 80)

    logger.info("fetch_vegetarian_recipes start (count=%d)", count)

    with _make_client() as client:
        recipe_urls = _collect_candidate_recipe_urls(settings, client, max_candidate_urls)

        recipes: list[Recipe] = []
        for idx, url in enumerate(recipe_urls, 1):
            if len(recipes) >= count:
                logger.info("reached target count %d, stopping detail fetch", count)
                break
            logger.info("[%d/%d] fetching detail (%d/%d so far)", idx, len(recipe_urls), len(recipes), count)
            try:
                recipe = fetch_recipe_detail(url, client=client)
                if _is_allowed_recipe(recipe):
                    recipes.append(recipe)
                else:
                    logger.info("  skipped recipe due to strict veg/main-course filter: %s", recipe.title)
            except (FetchError, httpx.RequestError) as e:
                logger.warning("  detail fetch failed: %r", e)
                continue

    logger.info("fetch_vegetarian_recipes done, returning %d recipes", len(recipes[:count]))
    return recipes[:count]
