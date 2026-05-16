import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from personal_shopper.cart.automation import (
    CartAutomationError,
    _add_recipe_ingredients_to_cart,
    _click_first,
    _detect_login_blocker,
    _is_logged_in,
    _launch_context,
    _write_login_debug_artifacts,
    process_cart_job,
)
from personal_shopper.config import Settings


def test_process_cart_job_returns_false_when_not_claimed(tmp_path: Path):
    settings = Settings(database_path=tmp_path / "db.sqlite")
    with patch("personal_shopper.cart.automation.claim_cart_job", return_value=False):
        assert not process_cart_job(settings.database_path, 1, settings)


def test_process_cart_job_fails_without_payload(tmp_path: Path):
    settings = Settings(database_path=tmp_path / "db.sqlite")
    with (
        patch("personal_shopper.cart.automation.claim_cart_job", return_value=True),
        patch("personal_shopper.cart.automation.get_cart_job_payload", return_value=None),
        patch("personal_shopper.cart.automation.mark_cart_job_failed") as mark_failed,
    ):
        assert not process_cart_job(settings.database_path, 1, settings)
        mark_failed.assert_called_once()


def test_process_cart_job_fails_without_credentials(tmp_path: Path):
    settings = Settings(database_path=tmp_path / "db.sqlite")
    payload = {"recipe_url": "https://www.delhaize.be/r/R0001"}
    with (
        patch("personal_shopper.cart.automation.claim_cart_job", return_value=True),
        patch("personal_shopper.cart.automation.get_cart_job_payload", return_value=payload),
        patch("personal_shopper.cart.automation.mark_cart_job_failed") as mark_failed,
    ):
        assert not process_cart_job(settings.database_path, 1, settings)
        mark_failed.assert_called_once()


def test_process_cart_job_success(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "db.sqlite",
        delhaize_username="u@example.com",
        delhaize_password="secret",
    )
    payload = {"recipe_url": "https://www.delhaize.be/r/R0001"}
    with (
        patch("personal_shopper.cart.automation.claim_cart_job", return_value=True),
        patch("personal_shopper.cart.automation.get_cart_job_payload", return_value=payload),
        patch("personal_shopper.cart.automation._add_recipe_ingredients_to_cart"),
        patch("personal_shopper.cart.automation.mark_cart_job_succeeded") as mark_ok,
    ):
        assert process_cart_job(settings.database_path, 1, settings)
        mark_ok.assert_called_once_with(settings.database_path, 1)


def test_click_first_raises_when_required_missing():
    class Locator:
        def count(self):
            return 0

    class Page:
        def locator(self, _selector):
            return Locator()

        def wait_for_timeout(self, _ms):
            return None

    try:
        _click_first(Page(), ["button:has-text('x')"])
    except CartAutomationError:
        pass
    else:
        raise AssertionError("Expected CartAutomationError")


def test_add_recipe_ingredients_works_with_mocked_playwright(monkeypatch):
    class Locator:
        def __init__(self, should_exist=True):
            self.should_exist = should_exist
            self.first = self

        def count(self):
            return 1 if self.should_exist else 0

        def nth(self, _index):
            return self

        def is_visible(self, timeout=None):
            return True

        def scroll_into_view_if_needed(self, timeout=None):
            return None

        def click(self, timeout=None):
            return None

        def fill(self, value, timeout=None):
            return None

    class Page:
        def goto(self, *_args, **_kwargs):
            return None

        def wait_for_url(self, *_args, **_kwargs):
            return None

        def wait_for_timeout(self, *_args, **_kwargs):
            return None

        def locator(self, _selector):
            return Locator(True)

    class Context:
        def new_page(self):
            return Page()

        def close(self):
            return None

    class Browser:
        def new_context(self):
            return Context()

        def close(self):
            return None

    class Chromium:
        def launch(self, headless=True, args=None):
            return Browser()

    class SyncPW:
        def __enter__(self):
            return SimpleNamespace(chromium=Chromium())

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_module = SimpleNamespace(sync_playwright=lambda: SyncPW(), TimeoutError=TimeoutError)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)

    _add_recipe_ingredients_to_cart(
        recipe_url="https://www.delhaize.be/r/R0001",
        username="u@example.com",
        password="secret",
    )


def test_launch_context_uses_persistent_profile(tmp_path: Path):
    profile = tmp_path / "profile"
    profile.mkdir()
    marker = object()

    chromium = SimpleNamespace(
        launch_persistent_context=lambda *args, **kwargs: marker,
        launch=lambda *args, **kwargs: None,
    )
    playwright = SimpleNamespace(chromium=chromium)
    context = _launch_context(playwright, profile)
    assert context is marker


def test_is_logged_in_detects_logged_in_signal():
    class Locator:
        def __init__(self, n):
            self._n = n

        def count(self):
            return self._n

    class Page:
        def locator(self, selector):
            if selector == "text=Mijn lijsten":
                return Locator(1)
            return Locator(0)

    assert _is_logged_in(Page())


def test_detect_login_blocker_recaptcha():
    class Locator:
        def __init__(self, n):
            self._n = n

        def count(self):
            return self._n

        def inner_text(self, timeout=None):
            return ""

    class Page:
        def locator(self, selector):
            if "recaptcha" in selector:
                return Locator(1)
            return Locator(0)

    assert _detect_login_blocker(Page()) is not None


def test_detect_login_blocker_text_marker():
    class Locator:
        def __init__(self, text="", n=0):
            self._text = text
            self._n = n

        def count(self):
            return self._n

        def inner_text(self, timeout=None):
            return self._text

    class Page:
        def locator(self, selector):
            if selector == "body":
                return Locator("Please verify you are human", 1)
            return Locator("", 0)

    blocker = _detect_login_blocker(Page())
    assert blocker is not None
    assert "anti-bot" in blocker


def test_click_first_skips_failed_click_then_succeeds():
    class ClickFail:
        def nth(self, _index):
            return self

        def count(self):
            return 1

        def is_visible(self, timeout=None):
            return True

        def scroll_into_view_if_needed(self, timeout=None):
            return None

        def click(self, timeout=None):
            raise RuntimeError("fail")

    class ClickOk:
        def nth(self, _index):
            return self

        def count(self):
            return 1

        def is_visible(self, timeout=None):
            return True

        def scroll_into_view_if_needed(self, timeout=None):
            return None

        def click(self, timeout=None):
            return None

    class Page:
        def locator(self, selector):
            if "first" in selector:
                return ClickFail()
            return ClickOk()

    assert _click_first(Page(), ["first", "second"])


def test_write_login_debug_artifacts_executes():
    class Locator:
        def __init__(self, n=0):
            self._n = n

        def count(self):
            return self._n

    class Frame:
        def __init__(self, url):
            self.url = url

    class Page:
        url = "https://www.delhaize.be/registration/welcome"
        frames = [Frame("https://www.delhaize.be/")]

        def screenshot(self, path, full_page=True):
            Path(path).write_bytes(b"x")

        def content(self):
            return "<html></html>"

        def locator(self, selector):
            mapping = {
                "input": 1,
                "input[type='password']": 0,
                "button": 2,
                "iframe[src*='recaptcha']": 1,
            }
            return Locator(mapping.get(selector, 0))

    _write_login_debug_artifacts(Page())
