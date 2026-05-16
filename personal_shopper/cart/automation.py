from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from personal_shopper.config import Settings
from personal_shopper.slack.store import (
    claim_cart_job,
    get_cart_job_payload,
    mark_cart_job_failed,
    mark_cart_job_succeeded,
)


class CartAutomationError(RuntimeError):
    pass


def process_cart_job(db_path: Path, job_id: int, settings: Settings) -> bool:
    if not claim_cart_job(db_path, job_id):
        return False

    payload = get_cart_job_payload(db_path, job_id)
    if payload is None:
        mark_cart_job_failed(db_path, job_id, "Cart job payload not found")
        return False

    if not settings.delhaize_username or not settings.delhaize_password:
        mark_cart_job_failed(db_path, job_id, "Missing DELHAIZE_USERNAME/DELHAIZE_PASSWORD")
        return False

    try:
        _add_recipe_ingredients_to_cart(
            recipe_url=payload["recipe_url"],
            username=settings.delhaize_username,
            password=settings.delhaize_password,
            profile_path=settings.delhaize_profile_path,
        )
    except Exception as exc:
        mark_cart_job_failed(db_path, job_id, str(exc))
        return False

    mark_cart_job_succeeded(db_path, job_id)
    return True


def _add_recipe_ingredients_to_cart(
    recipe_url: str,
    username: str,
    password: str,
    profile_path: Path | None = None,
) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise CartAutomationError("Playwright is not installed") from exc

    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_path)
        pages = getattr(context, "pages", [])
        page = pages[0] if pages else context.new_page()
        try:
            page.goto("https://www.delhaize.be/", wait_until="domcontentloaded")
            _dismiss_cookie_banner_if_present(page)

            if not _is_logged_in(page):
                page.goto(
                    "https://www.delhaize.be/registration/welcome",
                    wait_until="domcontentloaded",
                )
                _dismiss_cookie_banner_if_present(page)
                _perform_login(page, username, password)

            try:
                page.wait_for_url("**delhaize.be/**", timeout=20_000)
            except PlaywrightTimeoutError:
                pass

            page.goto(recipe_url, wait_until="domcontentloaded")
            _dismiss_cookie_banner_if_present(page)

            clicked = _click_first(
                page,
                [
                    "text=/Voeg\\s+\\d+\\s+producten toe aan je winkelmandje/i",
                    "text=/Voeg\\s+\\d+\\s+ingredienten toe aan je winkelmandje/i",
                    "text=/Voeg\\s+\\d+\\s+ingrediënten toe aan je winkelmandje/i",
                    "button:has-text('Voeg toe aan winkelkar')",
                    "button:has-text('Voeg toe aan winkelmandje')",
                    "button:has-text('Voeg producten toe aan je winkelmandje')",
                    "button:has-text('Voeg ingrediënten toe aan je winkelmandje')",
                    "button:has-text('Voeg')",
                    "button:has-text('Voeg ingrediënten toe')",
                    "button:has-text('Voeg ingredienten toe')",
                    "button:has-text('In winkelkar')",
                    "button:has-text('Winkelkar')",
                ],
                optional=True,
            )
            if not clicked:
                raise CartAutomationError("Could not find add-to-cart button on recipe page")

            page.wait_for_timeout(4000)
        finally:
            context.close()


def _launch_context(playwright, profile_path: Path | None):
    launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
    if profile_path is not None and profile_path.exists():
        return playwright.chromium.launch_persistent_context(
            str(profile_path),
            headless=True,
            args=launch_args,
        )
    browser = playwright.chromium.launch(headless=True, args=launch_args)
    return browser.new_context()


def _is_logged_in(page) -> bool:
    signals = [
        "text=Mijn lijsten",
        "text=Vaak gekocht",
        "a[href*='/my-lists']",
        "a[href*='/logout']",
    ]
    return any(page.locator(selector).count() > 0 for selector in signals)


def _perform_login(page, username: str, password: str) -> None:
    email = page.locator(
        "input[name='emailOrPhoneNumber'], input[type='email'], "
        "input[name*='email' i], input[id*='email' i]"
    ).first
    email.fill(username, timeout=20_000)

    clicked_continue = _click_first(
        page,
        [
            "button:has-text('Meld je aan')",
            "button:has-text('Aanmelden')",
            "button:has-text('Ga verder')",
            "button[type='submit']",
        ],
        optional=True,
    )
    if not clicked_continue:
        email.press("Enter")

    password_input = _wait_for_password_input(page)
    password_input.fill(password, timeout=20_000)

    _click_first(
        page,
        [
            "button:has-text('Aanmelden')",
            "button:has-text('Inloggen')",
            "button:has-text('Log in')",
            "button[type='submit']",
        ],
    )


def _wait_for_password_input(page):
    selectors = [
        "input[type='password']",
        "input[name*='password' i]",
        "input[id*='password' i]",
    ]
    for _ in range(4):
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator
        blocker = _detect_login_blocker(page)
        if blocker:
            _write_login_debug_artifacts(page)
            raise CartAutomationError(blocker)
        _click_first(
            page,
            [
                "button:has-text('Meld je aan')",
                "button:has-text('Aanmelden')",
                "button:has-text('Ga verder')",
                "button[type='submit']",
            ],
            optional=True,
        )
        page.wait_for_timeout(3000)
    _write_login_debug_artifacts(page)
    raise CartAutomationError("Password input did not appear after continue step")


def _detect_login_blocker(page) -> str | None:
    recaptcha_selector = "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']"
    if page.locator(recaptcha_selector).count() > 0:
        return "Delhaize requested reCAPTCHA again; manual login required."

    text_markers = [
        "controleer of je een robot bent",
        "verify you are human",
        "unusual traffic",
        "suspicious activity",
    ]
    body_text = (page.locator("body").inner_text(timeout=2000) or "").lower()
    for marker in text_markers:
        if marker in body_text:
            return f"Delhaize anti-bot gate detected: '{marker}'"
    return None


def _write_login_debug_artifacts(page) -> None:
    out_dir = Path("/tmp/opencode/delhaize-login-debug")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    png_path = out_dir / f"login-{stamp}.png"
    html_path = out_dir / f"login-{stamp}.html"
    txt_path = out_dir / f"login-{stamp}.txt"

    try:
        page.screenshot(path=str(png_path), full_page=True)
    except Exception:
        pass
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        frame_urls = [f.url for f in page.frames]
        input_count = page.locator("input").count()
        password_count = page.locator("input[type='password']").count()
        button_count = page.locator("button").count()
        recaptcha_count = page.locator("iframe[src*='recaptcha']").count()
        summary = [
            f"url={page.url}",
            f"input_count={input_count}",
            f"password_count={password_count}",
            f"button_count={button_count}",
            f"recaptcha_iframe_count={recaptcha_count}",
            "frames:",
            *frame_urls,
        ]
        txt_path.write_text("\n".join(summary), encoding="utf-8")
    except Exception:
        pass


def _dismiss_cookie_banner_if_present(page) -> None:
    _click_first(
        page,
        [
            "button:has-text('Accepteer')",
            "button:has-text('Alles accepteren')",
            "button:has-text('Akkoord')",
        ],
        optional=True,
    )


def _click_first(page, selectors: list[str], optional: bool = False) -> bool:
    for _ in range(4):
        for selector in selectors:
            locator = page.locator(selector)
            count = locator.count()
            if count == 0:
                continue
            for i in range(count):
                candidate = locator.nth(i)
                try:
                    if not candidate.is_visible(timeout=1000):
                        continue
                    candidate.scroll_into_view_if_needed(timeout=2000)
                    candidate.click(timeout=5000)
                    return True
                except Exception:
                    try:
                        candidate.click(timeout=5000, force=True)
                        return True
                    except Exception:
                        continue
        page.wait_for_timeout(1500)
    if optional:
        return False
    raise CartAutomationError(f"No clickable element found for selectors: {selectors}")
