import logging
import re
import sys
import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from personal_shopper.config import Settings, get_settings
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

_RECIPE_LINK_RE = re.compile(r"^/r/[A-Za-z0-9]+$")
_PREP_TIME_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)
_SERVINGS_RE = re.compile(r"(\d+)\s*porti", re.IGNORECASE)


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

    return Recipe(
        title=title,
        url=url,
        prep_time_min=prep_time_min,
        servings=servings,
        image_url=image_url,
    )


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

    listing_urls = [
        f"{settings.delhaize_base_url}/nl/plantbased",
        f"{settings.delhaize_base_url}/nl/recepten/salades",
        f"{settings.delhaize_base_url}/nl/recepten/soep/",
        f"{settings.delhaize_base_url}/nl/recepten/hoofdgerechten",
    ]

    logger.info("fetch_vegetarian_recipes start (count=%d)", count)
    logger.info("listing urls: %s", listing_urls)

    with _make_client() as client:
        recipe_urls: list[str] = []
        seen_urls: set[str] = set()

        for listing_url in listing_urls:
            if len(recipe_urls) >= count * 3:
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

        recipes: list[Recipe] = []
        for idx, url in enumerate(recipe_urls, 1):
            if len(recipes) >= count:
                logger.info("reached target count %d, stopping detail fetch", count)
                break
            logger.info("[%d/%d] fetching detail (%d/%d so far)", idx, len(recipe_urls), len(recipes), count)
            try:
                recipes.append(fetch_recipe_detail(url, client=client))
            except (FetchError, httpx.RequestError) as e:
                logger.warning("  detail fetch failed: %r", e)
                continue

    logger.info("fetch_vegetarian_recipes done, returning %d recipes", len(recipes[:count]))
    return recipes[:count]
